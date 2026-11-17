from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import models  # noqa: F401 - registra todos os models
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.limits import BodySizeLimitMiddleware
from app.modules.auditoria.router import router as auditoria_router
from app.modules.identidade.router import router as identidade_router
from app.modules.precificacao.router import router as precificacao_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Odonto System API", version="0.1.0")

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(IntegrityError)
    async def _integrity_conflict(request: Request, exc: IntegrityError):
        # Requisições simultâneas podem passar pelas checagens do service e esbarrar numa
        # constraint do banco (nome duplicado, segundo rascunho...). Isso é conflito, não 500.
        # A sessão é descartada (rollback) ao sair da dependência.
        return JSONResponse(
            status_code=409,
            content={"detail": "Conflito com dados existentes. Atualize e tente novamente."},
        )

    @app.get("/health", tags=["infra"])
    def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["infra"])
    def ready():
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        return {"status": "ok", "database": "ok"}

    app.include_router(identidade_router)
    app.include_router(auditoria_router)
    app.include_router(precificacao_router)
    return app


app = create_app()
