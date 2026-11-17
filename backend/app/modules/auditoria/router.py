import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import AuditLog
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    ip: str | None
    details: dict[str, Any] | None
    created_at: datetime


@router.get(
    "",
    response_model=list[AuditLogOut],
    dependencies=[Depends(require_roles(Role.ADMIN, Role.GESTOR))],
)
def list_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_tenant_db),
):
    # Sem filtro por clínica aqui de propósito: o RLS já restringe à clínica do token.
    return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
