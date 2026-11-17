"""Pacientes: cadastro, busca, auditoria de leitura, consentimentos e isolamento."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.pacientes.models import ConsentGivenBy, ConsentPurpose, Patient, PatientConsent

pytestmark = pytest.mark.integration

CPF_ANA = "529.982.247-25"
CPF_JOSE = "111.444.777-35"
CPF_RESP = "123.456.789-09"


def _login_as(client, make_clinic, role=Role.RECEPCAO):
    clinic, user, pw = make_clinic(role=role)
    return clinic, _auth(_login(client, user.email, pw).json()["access_token"])


def _create(client, h, **fields):
    body = {"full_name": "Ana Souza", "phone": "(11) 98765-4321", **fields}
    resp = client.post("/pacientes", json=body, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _actions(client, make_clinic, clinic):
    # A auditoria só é lida por admin/gestor; usa uma sessão de tenant direto.
    from app.core.audit import AuditLog

    with tenant_session(clinic.id) as s:
        return list(s.execute(select(AuditLog.action, AuditLog.details)).all())


# ---------- cadastro ----------


def test_create_read_update(client, make_clinic):
    clinic, h = _login_as(client, make_clinic)
    p = _create(client, h, cpf=CPF_ANA, social_name="Aninha", state="sp")
    assert p["cpf"] == "52998224725" and p["phone"] == "11987654321" and p["state"] == "SP"

    got = client.get(f"/pacientes/{p['id']}", headers=h)
    assert got.status_code == 200 and got.json()["social_name"] == "Aninha"

    patched = client.patch(
        f"/pacientes/{p['id']}", json={"city": "Campinas", "social_name": None}, headers=h
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["city"] == "Campinas" and patched.json()["social_name"] is None

    actions = _actions(client, make_clinic, clinic)
    names = [a for a, _ in actions]
    assert {"pacientes.cadastrado", "pacientes.ficha_lida", "pacientes.ficha_alterada"} <= set(
        names
    )
    changed = next(d for a, d in actions if a == "pacientes.ficha_alterada")
    assert changed == {"campos": ["city", "social_name"]}  # só nomes, nunca valores


def test_validation_rules(client, make_clinic):
    _, h = _login_as(client, make_clinic)
    _create(client, h, cpf=CPF_ANA)

    dup = client.post(
        "/pacientes", json={"full_name": "Outra", "phone": "11999990000", "cpf": CPF_ANA}, headers=h
    )
    assert dup.status_code == 409 and "CPF" in dup.json()["detail"]

    bad = client.post(
        "/pacientes", json={"full_name": "X", "phone": "11999990000", "cpf": "123"}, headers=h
    )
    assert bad.status_code == 422

    minor = {"full_name": "Criança", "phone": "11999990000", "birth_date": "2020-01-01"}
    resp = client.post("/pacientes", json=minor, headers=h)
    assert resp.status_code == 409 and "responsável" in resp.json()["detail"]
    _create(client, h, **minor, guardian_name="Mãe", guardian_cpf=CPF_RESP)

    p = _create(client, h, full_name="Sem Nome Depois", phone="11911112222")
    for field in ("full_name", "phone", "active"):
        resp = client.patch(f"/pacientes/{p['id']}", json={field: None}, headers=h)
        assert resp.status_code == 409, field


def test_same_cpf_allowed_in_other_clinic(client, make_clinic):
    _, ha = _login_as(client, make_clinic)
    _, hb = _login_as(client, make_clinic)
    _create(client, ha, cpf=CPF_ANA)
    _create(client, hb, cpf=CPF_ANA)


# ---------- busca ----------


def test_search_by_name_cpf_and_phone(client, make_clinic):
    clinic, h = _login_as(client, make_clinic)
    ana = _create(client, h, full_name="Ana Conceição Souza", cpf=CPF_ANA)
    jose = _create(client, h, full_name="José Silva", phone="1133334444", cpf=CPF_JOSE)
    _create(client, h, full_name="Mariana_50% Lima", phone="11955556666")

    def ids(busca):
        resp = client.get("/pacientes", params={"busca": busca}, headers=h)
        assert resp.status_code == 200, resp.text
        return {p["id"] for p in resp.json()}

    assert ids("conceicao ana") == {ana["id"]}  # sem acento, palavras em qualquer ordem
    assert ids("JOSÉ") == {jose["id"]}
    assert ids("111.444.777-35") == {jose["id"]}
    assert ids("3333-44") == {jose["id"]}  # trecho do telefone
    assert ids("_50%") == set(ids("mariana"))  # curingas do LIKE são escapados
    assert len(ids("%")) == 0
    assert len(ids(None)) == 3

    row = client.get("/pacientes", params={"busca": "ana souza"}, headers=h).json()[0]
    assert row["cpf_mascarado"] == "***.982.247-**" and "cpf" not in row

    searches = [d for a, d in _actions(client, make_clinic, clinic) if a == "pacientes.busca"]
    assert searches and all(set(d) == {"resultados", "com_termo"} for d in searches)


def test_inactive_hidden_by_default(client, make_clinic):
    _, h = _login_as(client, make_clinic)
    p = _create(client, h)
    client.patch(f"/pacientes/{p['id']}", json={"active": False}, headers=h)
    assert client.get("/pacientes", headers=h).json() == []
    found = client.get("/pacientes", params={"incluir_inativos": True}, headers=h).json()
    assert [x["id"] for x in found] == [p["id"]]


# ---------- consentimentos ----------


def test_consents_history_and_current(client, make_clinic):
    clinic, h = _login_as(client, make_clinic)
    p = _create(client, h)
    url = f"/pacientes/{p['id']}/consentimentos"
    body = {"purpose": "comunicacao", "granted": True, "term_version": "v1"}
    assert client.post(url, json=body, headers=h).status_code == 201
    assert client.post(url, json={**body, "granted": False}, headers=h).status_code == 201

    data = client.get(url, headers=h).json()
    assert data["atuais"]["comunicacao"]["granted"] is False
    assert data["atuais"]["uso_imagem"] is None
    assert [c["granted"] for c in data["historico"]] == [False, True]
    assert {"pacientes.consentimento_registrado", "pacientes.consentimentos_lidos"} <= {
        a for a, _ in _actions(client, make_clinic, clinic)
    }


def test_minor_consent_must_come_from_guardian(client, make_clinic):
    _, h = _login_as(client, make_clinic)
    kid = _create(client, h, birth_date=date(2020, 1, 1).isoformat(), guardian_name="Pai")
    url = f"/pacientes/{kid['id']}/consentimentos"
    body = {"purpose": "tratamento_dados", "granted": True}
    assert client.post(url, json=body, headers=h).status_code == 409
    assert client.post(url, json={**body, "given_by": "responsavel"}, headers=h).status_code == 201

    adult = _create(client, h, full_name="Adulto")
    resp = client.post(
        f"/pacientes/{adult['id']}/consentimentos",
        json={**body, "given_by": "responsavel"},
        headers=h,
    )
    assert resp.status_code == 409  # sem responsável cadastrado


def test_consents_are_append_only(client, make_clinic):
    clinic, h = _login_as(client, make_clinic)
    p = _create(client, h)
    client.post(
        f"/pacientes/{p['id']}/consentimentos",
        json={"purpose": "uso_imagem", "granted": True},
        headers=h,
    )
    for sql in ("UPDATE patient_consents SET granted = false", "DELETE FROM patient_consents"):
        with tenant_session(clinic.id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))


# ---------- papéis e isolamento ----------


@pytest.mark.parametrize("role", list(Role))
def test_whole_team_accesses_registry(client, make_clinic, role):
    _, h = _login_as(client, make_clinic, role)
    p = _create(client, h)
    assert client.get(f"/pacientes/{p['id']}", headers=h).status_code == 200


def test_requires_authentication(client):
    assert client.get("/pacientes").status_code == 401
    assert client.post("/pacientes", json={}).status_code == 401


def test_other_clinic_cannot_see_or_change(client, make_clinic):
    a, ha = _login_as(client, make_clinic)
    b, hb = _login_as(client, make_clinic)
    p = _create(client, ha, cpf=CPF_ANA)
    pid = p["id"]

    assert client.get(f"/pacientes/{pid}", headers=hb).status_code == 404
    assert client.patch(f"/pacientes/{pid}", json={"city": "X"}, headers=hb).status_code == 404
    assert client.get(f"/pacientes/{pid}/consentimentos", headers=hb).status_code == 404
    consent = {"purpose": "comunicacao", "granted": True}
    assert (
        client.post(f"/pacientes/{pid}/consentimentos", json=consent, headers=hb).status_code == 404
    )
    assert client.get("/pacientes", params={"busca": "ana"}, headers=hb).json() == []
    assert client.get("/pacientes", params={"busca": CPF_ANA}, headers=hb).json() == []

    with tenant_session(b.id) as s:
        assert s.scalar(select(func.count()).select_from(Patient)) == 0
        # FK composta: B não consegue pendurar um consentimento no paciente de A.
        s.add(
            PatientConsent(
                clinic_id=b.id,
                patient_id=uuid.UUID(pid),
                purpose=ConsentPurpose.COMUNICACAO,
                granted=True,
                given_by=ConsentGivenBy.PACIENTE,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()
    with tenant_session(a.id) as s:
        assert s.get(Patient, uuid.UUID(pid)).city is None
