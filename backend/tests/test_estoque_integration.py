"""Estoque (cadastro de materiais): CRUD, visibilidade de custo, papéis e isolamento."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from test_auth_integration import _auth, _login

from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.estoque.models import Material

pytestmark = pytest.mark.integration

RESINA = {"name": "Resina A2", "unit": "g", "category": "Dentística", "unit_cost": "3.2000"}


def _admin(client, make_clinic):
    clinic, user, pw = make_clinic(role=Role.ADMIN)
    return clinic, _auth(_login(client, user.email, pw).json()["access_token"])


def _member(client, add_member, clinic, role):
    user, pw = add_member(clinic, role)
    return _auth(_login(client, user.email, pw).json()["access_token"])


def test_crud_and_deactivate(client, make_clinic):
    _, h = _admin(client, make_clinic)
    resp = client.post("/estoque/materiais", json=RESINA, headers=h)
    assert resp.status_code == 201, resp.text
    material = resp.json()
    assert material["unit_cost"] == "3.2000" and material["active"] is True

    dup = client.post("/estoque/materiais", json={**RESINA, "name": "resina a2"}, headers=h)
    assert dup.status_code == 409

    url = f"/estoque/materiais/{material['id']}"
    patched = client.patch(url, json={"unit_cost": "3.5", "active": False}, headers=h)
    assert patched.status_code == 200 and patched.json()["unit_cost"] == "3.5000"

    assert client.get("/estoque/materiais", headers=h).json() == []
    listed = client.get("/estoque/materiais?incluir_inativos=true", headers=h).json()
    assert [m["name"] for m in listed] == ["Resina A2"]

    actions = {r["action"] for r in client.get("/auditoria", headers=h).json()}
    assert {"estoque.material_criado", "estoque.material_alterado"} <= actions


def test_cost_visible_only_to_managers(client, make_clinic, add_member):
    clinic, h = _admin(client, make_clinic)
    material = client.post("/estoque/materiais", json=RESINA, headers=h).json()
    for role in (Role.DENTISTA, Role.ASB):
        hr = _member(client, add_member, clinic, role)
        listed = client.get("/estoque/materiais", headers=hr).json()
        assert listed and "unit_cost" not in listed[0]
        one = client.get(f"/estoque/materiais/{material['id']}", headers=hr).json()
        assert "unit_cost" not in one
        assert client.post("/estoque/materiais", json=RESINA, headers=hr).status_code == 403
        url = f"/estoque/materiais/{material['id']}"
        assert client.patch(url, json={"unit_cost": "0"}, headers=hr).status_code == 403
    hr = _member(client, add_member, clinic, Role.RECEPCAO)
    assert client.get("/estoque/materiais", headers=hr).status_code == 403


def test_other_clinic_cannot_see_or_change(client, make_clinic):
    clinic_a, h_a = _admin(client, make_clinic)
    clinic_b, h_b = _admin(client, make_clinic)
    material = client.post("/estoque/materiais", json=RESINA, headers=h_a).json()
    url = f"/estoque/materiais/{material['id']}"

    assert client.get("/estoque/materiais", headers=h_b).json() == []
    assert client.get(url, headers=h_b).status_code == 404
    assert client.patch(url, json={"unit_cost": "0"}, headers=h_b).status_code == 404
    # B pode ter material com o mesmo nome: a unicidade é por clínica.
    assert client.post("/estoque/materiais", json=RESINA, headers=h_b).status_code == 201

    with tenant_session(clinic_b.id) as s:
        assert [m.name for m in s.scalars(select(Material))] == ["Resina A2"]
        assert all(m.clinic_id == clinic_b.id for m in s.scalars(select(Material)))
    with tenant_session(clinic_b.id) as s:
        s.add(Material(clinic_id=clinic_a.id, name="X", unit="un", unit_cost=1))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.commit()
