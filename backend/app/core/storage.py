"""Armazenamento de arquivos (anexos, raio-X).

Dois backends, escolhidos por configuração (`STORAGE_BACKEND`), com a mesma interface
(`put`, `get`, `delete`) e as mesmas chaves (`<clinic_id>/<uuid>.<ext>`):

- `local` (padrão, sem custo): disco em `STORAGE_DIR`, uma pasta por clínica.
- `s3`: qualquer serviço compatível com S3 (AWS S3 em sa-east-1, Cloudflare R2, Backblaze B2,
  MinIO…), via `boto3` (`pip install -e ".[s3]"`). Bucket privado: os arquivos só saem pela
  API, que confere papel e clínica (a linha do banco passa pelo RLS) antes de ler a chave.

Trocar de backend não muda o banco: basta copiar os arquivos mantendo as chaves.
O nome do arquivo é sempre gerado pelo sistema (UUID), nunca o enviado pelo usuário.
"""

import logging
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings

_KEY = re.compile(r"^[0-9a-f-]{36}/[0-9a-f-]{36}\.[a-z0-9]{1,8}$")


log = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class StorageUnavailable(StorageError):
    """O serviço de armazenamento falhou (rede, permissão): tente de novo."""


class Backend(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def make_key(clinic_id: uuid.UUID, file_id: uuid.UUID, extension: str) -> str:
    return f"{clinic_id}/{file_id}.{extension}"


def check_key(key: str) -> str:
    if not _KEY.fullmatch(key):
        raise StorageError("Chave de arquivo inválida.")
    return key


# ---------- disco local ----------


class LocalBackend:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if self.root not in path.parents:
            raise StorageError("Chave de arquivo inválida.")
        return path

    def put(self, key: str, data: bytes) -> None:
        """Grava de forma atômica (arquivo temporário + rename)."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise StorageError("Arquivo não encontrado no armazenamento.") from None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


# ---------- S3 e compatíveis ----------


class S3Backend:
    """`client` é um cliente boto3 de S3 (ou qualquer objeto com put/get/delete_object)."""

    def __init__(self, client: Any, bucket: str, prefix: str = ""):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    def _name(self, key: str) -> str:
        return self.prefix + check_key(key)

    def put(self, key: str, data: bytes) -> None:
        name = self._name(key)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=name,
                Body=data,
                ServerSideEncryption="AES256",  # criptografia em repouso (LGPD, dado de saúde)
            )
        except Exception as exc:  # botocore.ClientError, rede etc., sem importar o botocore
            log.exception("falha ao gravar no S3: %s", name)
            raise StorageUnavailable("Não foi possível gravar o arquivo. Tente de novo.") from exc

    def get(self, key: str) -> bytes:
        name = self._name(key)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=name)
            return obj["Body"].read()
        except Exception as exc:
            if "NoSuchKey" in type(exc).__name__ or "NoSuchKey" in str(exc):
                raise StorageError("Arquivo não encontrado no armazenamento.") from None
            log.exception("falha ao ler do S3: %s", name)
            raise StorageUnavailable("Não foi possível ler o arquivo. Tente de novo.") from exc

    def delete(self, key: str) -> None:
        name = self._name(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=name)
        except Exception as exc:
            log.exception("falha ao apagar do S3: %s", name)
            raise StorageUnavailable("Não foi possível apagar o arquivo.") from exc


def _s3_client():
    settings = get_settings()
    try:
        import boto3
    except ImportError:  # pragma: no cover - depende do ambiente
        raise StorageError('STORAGE_BACKEND=s3 exige o boto3: pip install -e ".[s3]"') from None
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


@lru_cache
def backend() -> Backend:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Backend(_s3_client(), settings.s3_bucket or "", settings.s3_prefix)
    return LocalBackend(Path(settings.storage_dir))


# Atalhos usados pelos módulos.


def put(key: str, data: bytes) -> None:
    backend().put(key, data)


def get(key: str) -> bytes:
    return backend().get(key)


def delete(key: str) -> None:
    """Só para desfazer uma gravação cuja transação falhou."""
    backend().delete(key)
