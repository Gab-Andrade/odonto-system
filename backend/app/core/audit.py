"""Log de auditoria (LGPD): quem fez o quê, em qual registro, quando.

A tabela é append-only para o role da aplicação (UPDATE/DELETE revogados na migração)
e isolada por clínica via RLS.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.context import CurrentUser
from app.core.models import Base, TenantMixin, UUIDPkMixin


class AuditLog(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


def record(
    session: Session,
    user: CurrentUser,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Adiciona um registro de auditoria à sessão (o commit fica com quem chama)."""
    entry = AuditLog(
        clinic_id=user.clinic_id,
        user_id=user.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        ip=request.client.host if request and request.client else None,
        user_agent=(request.headers.get("user-agent", "")[:300] or None) if request else None,
    )
    session.add(entry)
    return entry
