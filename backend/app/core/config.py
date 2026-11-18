from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-troque-em-producao"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # A aplicação conecta com um role SEM privilégio de dono das tabelas,
    # para que o Row-Level Security seja sempre aplicado.
    database_url: str = "postgresql+psycopg://odonto_app:odonto_app@localhost:5432/odonto"
    # As migrações rodam com o role dono do schema.
    migrations_database_url: str = "postgresql+psycopg://odonto:odonto@localhost:5432/odonto"

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:5173"]

    # Fuso usado para "hoje" em regras de vigência. Vira configuração por clínica
    # quando houver clínicas em mais de um fuso.
    clinic_timezone: str = "America/Sao_Paulo"

    # Tamanho máximo do corpo de qualquer requisição (o maior caso é o upload de planilha,
    # limitado a 2 MB; a folga cobre o envelope multipart).
    max_request_bytes: int = 3 * 1024 * 1024

    # Arquivos (raio-X). "local": pasta em disco (fora do controle de versão).
    # "s3": serviço compatível com S3 (AWS, Cloudflare R2, Backblaze, MinIO), com boto3.
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: str = "var/arquivos"
    s3_bucket: str | None = None
    s3_prefix: str = ""
    s3_region: str | None = None
    s3_endpoint_url: str | None = None  # vazio = AWS; preencha para R2/B2/MinIO
    s3_access_key_id: str | None = None  # vazio = credenciais do ambiente (IAM role etc.)
    s3_secret_access_key: str | None = None
    # Tamanho máximo de um arquivo DICOM (só a rota de envio de exame aceita corpo maior).
    max_dicom_bytes: int = 30 * 1024 * 1024

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET precisa ser definido (mín. 32 caracteres) em produção")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("STORAGE_BACKEND=s3 exige S3_BUCKET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
