import pytest

from app.core.roles import Role
from app.modules.identidade.models import ClinicMembership

pytestmark = pytest.mark.integration


def _login(client, email, password, clinic_id=None):
    body = {"email": email, "password": password}
    if clinic_id:
        body["clinic_id"] = str(clinic_id)
    return client.post("/auth/login", json=body)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_and_me(client, make_clinic):
    clinic, user, password = make_clinic(role=Role.DENTISTA)
    resp = _login(client, user.email.upper(), password)  # e-mail sem diferenciar maiúsculas
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["role"] == "dentista"
    assert data["clinic"]["id"] == str(clinic.id)

    me = client.get("/auth/me", headers=_auth(data["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == user.email


def test_wrong_password_and_unknown_email(client, make_clinic):
    _, user, _ = make_clinic()
    assert _login(client, user.email, "errada").status_code == 401
    assert _login(client, "ninguem@exemplo.com", "qualquer").status_code == 401


def test_multiple_clinics_require_selection(client, make_clinic):
    c1, user, password = make_clinic()
    c2, _, _ = make_clinic(user=user)

    resp = _login(client, user.email, password)
    assert resp.status_code == 409
    assert {c["id"] for c in resp.json()["clinics"]} == {str(c1.id), str(c2.id)}

    resp = _login(client, user.email, password, clinic_id=c2.id)
    assert resp.status_code == 200
    assert resp.json()["clinic"]["id"] == str(c2.id)


def test_revoked_membership_cuts_access_immediately(client, make_clinic, db_session):
    clinic, user, password = make_clinic()
    token = _login(client, user.email, password).json()["access_token"]
    assert client.get("/auth/me", headers=_auth(token)).status_code == 200

    m = db_session.query(ClinicMembership).filter_by(user_id=user.id).one()
    m.active = False
    db_session.commit()

    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_audit_listing_is_role_restricted_and_isolated(client, make_clinic):
    ca, admin_a, pw = make_clinic(role=Role.ADMIN)
    cb, admin_b, _ = make_clinic(role=Role.ADMIN)
    _, dentista, _ = make_clinic(role=Role.DENTISTA)

    token_a = _login(client, admin_a.email, pw).json()["access_token"]
    _login(client, admin_b.email, pw)
    token_d = _login(client, dentista.email, pw).json()["access_token"]

    logs = client.get("/auditoria", headers=_auth(token_a))
    assert logs.status_code == 200
    # Admin A vê só o próprio login, não o do admin B.
    assert [(r["action"], r["user_id"]) for r in logs.json()] == [("auth.login", str(admin_a.id))]

    assert client.get("/auditoria", headers=_auth(token_d)).status_code == 403


def test_team_lists_only_active_members_of_own_clinic(client, make_clinic, add_member, db_session):
    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    dentist, _ = add_member(clinic, Role.DENTISTA)
    gone, _ = add_member(clinic, Role.ASB)
    db_session.query(ClinicMembership).filter_by(user_id=gone.id).update({"active": False})
    db_session.commit()
    make_clinic(role=Role.ADMIN)  # outra clínica

    h = _auth(_login(client, admin.email, pw).json()["access_token"])
    r = client.get("/auth/equipe", headers=h)
    assert r.status_code == 200
    ids = {m["user_id"] for m in r.json()}
    assert ids == {str(admin.id), str(dentist.id)}
    assert all("email" not in m for m in r.json())
    assert client.get("/auth/equipe").status_code == 401
