"""Armazenamento de arquivos (anexos, raio-X).

Por enquanto em disco local (`STORAGE_DIR`), uma pasta por clínica e o nome do arquivo
gerado pelo sistema (UUID), nunca o enviado pelo usuário. A interface (`put`, `get`,
`delete`) é a que um armazenamento S3 vai implementar quando entrar (PLANO, decisão em
aberto sobre o storage S3 local).

O acesso é sempre pela API: a rota confere papel e clínica (a linha do banco passa pelo
RLS) antes de ler o arquivo pela chave guardada.
"""

import os
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

_KEY = re.compile(r"^[0-9a-f-]{36}/[0-9a-f-]{36}\.[a-z0-9]{1,8}$")


class StorageError(Exception):
    pass


def _root() -> Path:
    return Path(get_settings().storage_dir).resolve()


def make_key(clinic_id: uuid.UUID, file_id: uuid.UUID, extension: str) -> str:
    return f"{clinic_id}/{file_id}.{extension}"


def _path(key: str) -> Path:
    if not _KEY.fullmatch(key):
        raise StorageError("Chave de arquivo inválida.")
    path = (_root() / key).resolve()
    if _root() not in path.parents:
        raise StorageError("Chave de arquivo inválida.")
    return path


def put(key: str, data: bytes) -> None:
    """Grava de forma atômica (arquivo temporário + rename)."""
    path = _path(key)
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


def get(key: str) -> bytes:
    try:
        return _path(key).read_bytes()
    except FileNotFoundError:
        raise StorageError("Arquivo não encontrado no armazenamento.") from None


def delete(key: str) -> None:
    """Só para desfazer uma gravação cuja transação falhou."""
    try:
        _path(key).unlink()
    except FileNotFoundError:
        pass
