"""Isolamento entre clínicas (RLS) e auditoria append-only."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core import audit
from app.core.audit import AuditLog
from app.core.context import CurrentUser
from app.core.db import get_sessionmaker, tenant_session
from app.core.roles import Role

pytestmark = pytest.mark.integration


def _log(clinic_id, user_id, action):
    with tenant_session(clinic_id) as s:
        audit.record(s, CurrentUser(user_id, clinic_id, Role.ADMIN), action)
        s.commit()


def test_clinic_sees_only_its_rows(make_clinic):
    a, ua, _ = make_clinic()
    b, ub, _ = make_clinic()
    _log(a.id, ua.id, "a.1")
    _log(a.id, ua.id, "a.2")
    _log(b.id, ub.id, "b.1")

    with tenant_session(a.id) as s:
        assert sorted(s.scalars(select(AuditLog.action))) == ["a.1", "a.2"]
    with tenant_session(b.id) as s:
        assert list(s.scalars(select(AuditLog.action))) == ["b.1"]


def test_tenant_survives_commit(make_clinic):
    """O tenant precisa valer também nas transações seguintes da mesma sessão."""
    a, ua, _ = make_clinic()
    with tenant_session(a.id) as s:
        audit.record(s, CurrentUser(ua.id, a.id, Role.ADMIN), "primeira")
        s.commit()
        audit.record(s, CurrentUser(ua.id, a.id, Role.ADMIN), "segunda")
        s.commit()
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 2


def test_without_tenant_sees_nothing(make_clinic):
    a, ua, _ = make_clinic()
    _log(a.id, ua.id, "x")
    with get_sessionmaker()() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_cannot_write_into_other_clinic(make_clinic):
    a, ua, _ = make_clinic()
    b, _, _ = make_clinic()
    with tenant_session(a.id) as s:
        s.add(AuditLog(clinic_id=b.id, user_id=ua.id, action="invasao"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.commit()


def test_audit_is_append_only(make_clinic):
    a, ua, _ = make_clinic()
    _log(a.id, ua.id, "x")
    for sql in ("UPDATE audit_logs SET action = 'y'", "DELETE FROM audit_logs"):
        with tenant_session(a.id) as s:
            s.execute(select(1))  # abre a transação com o tenant aplicado
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))


def test_app_role_cannot_bypass_rls(db_session):
    row = db_session.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    assert row == (False, False)


def test_unknown_tenant_sees_nothing(make_clinic):
    a, ua, _ = make_clinic()
    _log(a.id, ua.id, "x")
    with tenant_session(uuid.uuid4()) as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 0
