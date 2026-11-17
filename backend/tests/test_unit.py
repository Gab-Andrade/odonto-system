import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import DEV_JWT_SECRET, Settings
from app.core.rls import enable_tenant_rls
from app.core.roles import Role
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_password_hash_roundtrip():
    hashed = hash_password("minha-senha")
    assert hashed.startswith("$argon2id$")
    assert verify_password("minha-senha", hashed)
    assert not verify_password("outra-senha", hashed)


def test_token_roundtrip():
    uid, cid = uuid.uuid4(), uuid.uuid4()
    payload = decode_access_token(create_access_token(uid, cid, Role.DENTISTA))
    assert payload["sub"] == str(uid)
    assert payload["cid"] == str(cid)
    assert payload["role"] == "dentista"


def test_expired_token_rejected():
    token = create_access_token(uuid.uuid4(), uuid.uuid4(), Role.ADMIN, expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_rejected():
    token = create_access_token(uuid.uuid4(), uuid.uuid4(), Role.ADMIN)
    forged = jwt.encode(
        {**jwt.decode(token, options={"verify_signature": False}), "role": "admin"},
        "outro-segredo-qualquer-com-tamanho",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_protected_route_requires_token():
    with TestClient(app) as client:
        assert client.get("/auth/me").status_code == 401
        resp = client.get("/auth/me", headers={"Authorization": "Bearer lixo"})
        assert resp.status_code == 401


def test_production_requires_real_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(environment="production", jwt_secret=DEV_JWT_SECRET)
    Settings(environment="production", jwt_secret="x" * 32)


def test_rls_sql_forces_policy():
    stmts = enable_tenant_rls("patients")
    assert "FORCE ROW LEVEL SECURITY" in stmts[1]
    assert "WITH CHECK" in stmts[2]
