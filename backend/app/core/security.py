import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.roles import Role

_password_hash = PasswordHash.recommended()  # argon2id


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


@lru_cache
def _dummy_hash() -> str:
    return hash_password("senha-inexistente-para-tempo-constante")


def burn_password_check(password: str) -> None:
    """Gasta o mesmo tempo de uma verificação real quando o usuário não existe,
    para não revelar por tempo de resposta quais e-mails estão cadastrados."""
    verify_password(password, _dummy_hash())


def create_access_token(
    user_id: uuid.UUID, clinic_id: uuid.UUID, role: Role, *, expires_minutes: int | None = None
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_minutes
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "cid": str(clinic_id),
        "role": role.value,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Levanta jwt.InvalidTokenError se o token for inválido ou expirado."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "cid", "typ"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload
