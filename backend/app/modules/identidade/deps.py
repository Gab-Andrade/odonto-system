"""Dependências FastAPI de autenticação, papéis e sessão por clínica.

Uso num endpoint de outro módulo:

    @router.get("/pacientes")
    def listar(
        user: CurrentUser = Depends(require_roles(Role.DENTISTA, Role.RECEPCAO)),
        db: Session = Depends(get_tenant_db),
    ): ...
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.db import get_db, tenant_session
from app.core.roles import Role
from app.core.security import decode_access_token
from app.modules.identidade.service import session_role

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if creds is None:
        raise _UNAUTHORIZED
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
        clinic_id = uuid.UUID(payload["cid"])
        issued_ms = int(payload.get("iat_ms", int(payload["iat"]) * 1000))
        issued_at = datetime.fromtimestamp(issued_ms / 1000, UTC)
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError, OverflowError):
        raise _UNAUTHORIZED from None

    role = session_role(db, user_id, clinic_id, issued_at)
    if role is None:
        raise _UNAUTHORIZED
    # O papel vem do banco, não do token: mudança de papel vale imediatamente.
    return CurrentUser(user_id=user_id, clinic_id=clinic_id, role=role)


def require_roles(*roles: Role) -> Callable[..., CurrentUser]:
    allowed = frozenset(roles)

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão")
        return user

    return _dep


def get_tenant_db(user: CurrentUser = Depends(get_current_user)) -> Iterator[Session]:
    with tenant_session(user.clinic_id) as session:
        yield session
