from functools import lru_cache

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

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET precisa ser definido (mín. 32 caracteres) em produção")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
