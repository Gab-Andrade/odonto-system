"""Engine, sessões e aplicação do tenant (clínica) em cada transação."""

import uuid
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

TENANT_KEY = "clinic_id"


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, transaction, connection) -> None:
    """Define `app.clinic_id` no início de TODA transação da sessão.

    `set_config(..., true)` vale só até o fim da transação; por isso o valor é
    reaplicado a cada nova transação (ex.: depois de um commit no meio do request).
    As policies de RLS leem esse valor.
    """
    clinic_id = session.info.get(TENANT_KEY)
    if clinic_id is not None:
        connection.execute(
            text("select set_config('app.clinic_id', :cid, true)"), {"cid": str(clinic_id)}
        )


def get_db() -> Iterator[Session]:
    """Sessão sem tenant: só enxerga tabelas globais (clínicas, usuários, vínculos)."""
    with get_sessionmaker()() as session:
        yield session


def tenant_session(clinic_id: uuid.UUID) -> Session:
    """Sessão restrita a uma clínica pelo RLS."""
    session = get_sessionmaker()()
    session.info[TENANT_KEY] = clinic_id
    return session
