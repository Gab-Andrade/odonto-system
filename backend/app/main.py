from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import models  # noqa: F401 - registra todos os models
from app.core.config import get_settings
from app.core.db import get_engine
from app.modules.auditoria.router import router as auditoria_router
from app.modules.identidade.router import router as identidade_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Odonto System API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
    return app


app = create_app()
