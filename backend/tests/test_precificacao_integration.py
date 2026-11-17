import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.precificacao.models import (
    PriceAssignment,
    PriceItem,
    PriceSnapshot,
    PriceTable,
    PriceTableVersion,
    ScopeType,
)
from app.modules.precificacao.service import today

pytestmark = pytest.mark.integration

BASE_ITEMS = [
    {"procedure_code": "PROFILAXIA", "description": "Profilaxia", "price": "120.00"},
    {"procedure_code": "RESTAURACAO", "description": "Restauração em resina", "price": "200.00"},
]


# ---------- helpers ----------


def _admin(client, make_clinic):
    clinic, user, pw = make_clinic(role=Role.ADMIN)
    return clinic, user, _auth(_login(client, user.email, pw).json()["access_token"])


def _member(client, add_member, clinic, role):
    user, pw = add_member(clinic, role)
    return user, _auth(_login(client, user.email, pw).json()["access_token"])


def _create_table(client, h, name, **extra):
    resp = client.post("/precificacao/tabelas", json={"name": name, **extra}, headers=h)
    assert resp.status_code == 201, resp.text
    table = resp.json()
    draft = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()[0]
    return table, draft


def _put_items(client, h, table, version, items):
    url = f"/precificacao/tabelas/{table['id']}/versoes/{version['id']}/itens"
    return client.put(url, json={"items": items}, headers=h)


def _publish(client, h, table, version, valid_from=None):
    url = f"/precificacao/tabelas/{table['id']}/versoes/{version['id']}/publicar"
    body = {"valid_from": str(valid_from)} if valid_from else {}
    return client.post(url, json=body, headers=h)


def _assign(client, h, table, scope_type="clinica", scope_id=None, priority=None):
    body = {"table_id": table["id"], "scope_type": scope_type}
    if scope_id:
        body["scope_id"] = str(scope_id)
    if priority is not None:
        body["priority"] = priority
    return client.post("/precificacao/atribuicoes", json=body, headers=h)


def _resolve(client, h, code, **ctx):
    body = {"procedure_code": code, **{k: str(v) for k, v in ctx.items()}}
    return client.post("/precificacao/resolver", json=body, headers=h)


def _base_table(client, h):
    table, draft = _create_table(client, h, "Tabela Base")
    assert _put_items(client, h, table, draft, BASE_ITEMS).status_code == 200
    assert _publish(client, h, table, draft).status_code == 200
    assert _assign(client, h, table).status_code == 201
    return table


# ---------- fluxo feliz ----------


def test_table_lifecycle_and_resolution(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    table = _base_table(client, h)

    versions = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()
    assert [(v["version"], v["status"]) for v in versions] == [(1, "publicada")]
    assert versions[0]["valid_from"] == str(today())

    resp = _resolve(client, h, "RESTAURACAO")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["price"] == "200.00"
    assert data["description"] == "Restauração em resina"
    assert data["trace"][0]["resultado"] == "encontrado"
    assert data["trace"][0]["calculo"][0]["origem"] == "item da tabela"


def test_inheritance_with_override_and_dentist_priority(client, make_clinic, add_member):
    clinic, _, h = _admin(client, make_clinic)
    dentist, _ = _member(client, add_member, clinic, Role.DENTISTA)
    base = _base_table(client, h)

    child, draft = _create_table(
        client, h, "Dr. Especialista", parent_table_id=base["id"], adjustment_pct="15"
    )
    override = [{"procedure_code": "RESTAURACAO", "description": "Restauração", "price": "260.00"}]
    assert _put_items(client, h, child, draft, override).status_code == 200
    assert _publish(client, h, child, draft).status_code == 200
    assert _assign(client, h, child, "dentista", dentist.id).status_code == 201

    # Herdado da base com +15%.
    r = _resolve(client, h, "PROFILAXIA", dentist_id=dentist.id).json()
    assert r["price"] == "138.00"
    assert r["table_id"] == child["id"]
    steps = r["trace"][0]["calculo"]
    assert [s["valor"] for s in steps] == ["120.00", "138.00"]
    assert steps[1]["ajuste_pct"] == "15.0000"

    # Override do dentista.
    assert _resolve(client, h, "RESTAURACAO", dentist_id=dentist.id).json()["price"] == "260.00"
    # Sem dentista: tabela da clínica.
    assert _resolve(client, h, "PROFILAXIA").json()["price"] == "120.00"


def test_missing_procedure_falls_back_and_404_with_trace(client, make_clinic, add_member):
    clinic, _, h = _admin(client, make_clinic)
    dentist, _ = _member(client, add_member, clinic, Role.DENTISTA)
    _base_table(client, h)

    # Tabela do dentista sem herança e só com um procedimento.
    own, draft = _create_table(client, h, "Só implante")
    implant = [{"procedure_code": "IMPLANTE", "description": "Implante", "price": "3500.00"}]
    _put_items(client, h, own, draft, implant)
    _publish(client, h, own, draft)
    _assign(client, h, own, "dentista", dentist.id)

    r = _resolve(client, h, "PROFILAXIA", dentist_id=dentist.id).json()
    assert r["price"] == "120.00"  # caiu para a tabela da clínica
    assert [t["resultado"] for t in r["trace"]] == ["procedimento ausente na tabela", "encontrado"]

    resp = _resolve(client, h, "CLAREAMENTO", dentist_id=dentist.id)
    assert resp.status_code == 404
    assert len(resp.json()["trace"]) == 2


def test_published_version_is_immutable_and_new_draft_copies(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    table = _base_table(client, h)
    v1 = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()[0]

    assert _put_items(client, h, table, v1, BASE_ITEMS[:1]).status_code == 409

    resp = client.post(f"/precificacao/tabelas/{table['id']}/versoes", headers=h)
    assert resp.status_code == 201
    v2 = resp.json()
    assert v2["version"] == 2
    url = f"/precificacao/tabelas/{table['id']}/versoes/{v2['id']}/itens"
    assert len(client.get(url, headers=h).json()) == 2

    # Só um rascunho por vez.
    assert client.post(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).status_code == 409


def test_future_version_and_frozen_snapshot(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    table = _base_table(client, h)

    snap = client.post(
        "/precificacao/snapshots", json={"procedure_code": "PROFILAXIA"}, headers=h
    ).json()
    assert snap["price"] == "120.00"

    v2 = client.post(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()
    new = [{**BASE_ITEMS[0], "price": "150.00"}, BASE_ITEMS[1]]
    _put_items(client, h, table, v2, new)
    tomorrow = today() + timedelta(days=1)
    assert _publish(client, h, table, v2, valid_from=tomorrow).status_code == 200

    assert _resolve(client, h, "PROFILAXIA").json()["price"] == "120.00"
    assert _resolve(client, h, "PROFILAXIA", effective_on=tomorrow).json()["price"] == "150.00"

    again = client.get(f"/precificacao/snapshots/{snap['id']}", headers=h).json()
    assert again["price"] == "120.00"
    assert again["trace"] == snap["trace"]


def test_publish_in_past_rejected(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    table, draft = _create_table(client, h, "T")
    _put_items(client, h, table, draft, BASE_ITEMS)
    assert (
        _publish(client, h, table, draft, valid_from=today() - timedelta(days=1)).status_code == 409
    )


def test_assignment_rules(client, make_clinic, add_member):
    clinic, _, h = _admin(client, make_clinic)
    _, outsider, _ = make_clinic(role=Role.DENTISTA)
    asb, _ = add_member(clinic, Role.ASB)
    table = _base_table(client, h)

    assert _assign(client, h, table).status_code == 409  # duplicada
    assert _assign(client, h, table, "dentista").status_code == 409  # sem scope_id
    # Dentista de outra clínica não pode receber tabela desta.
    assert _assign(client, h, table, "dentista", outsider.id).status_code == 409
    # Membro da clínica que não é dentista também não.
    assert _assign(client, h, table, "dentista", asb.id).status_code == 409

    assignments = client.get("/precificacao/atribuicoes", headers=h).json()
    assert len(assignments) == 1 and assignments[0]["priority"] == 30
    aid = assignments[0]["id"]
    assert client.delete(f"/precificacao/atribuicoes/{aid}", headers=h).status_code == 204
    assert _resolve(client, h, "PROFILAXIA").status_code == 404


def test_archive_rules(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    base = _base_table(client, h)
    url = f"/precificacao/tabelas/{base['id']}"
    assert client.patch(url, json={"status": "arquivada"}, headers=h).status_code == 409

    child, _ = _create_table(client, h, "Filha", parent_table_id=base["id"])
    child_url = f"/precificacao/tabelas/{child['id']}"
    aid = client.get("/precificacao/atribuicoes", headers=h).json()[0]["id"]
    client.delete(f"/precificacao/atribuicoes/{aid}", headers=h)

    # Pai com filha ativa não arquiva; arquivando a filha antes, arquiva.
    assert client.patch(url, json={"status": "arquivada"}, headers=h).status_code == 409
    assert client.patch(child_url, json={"status": "arquivada"}, headers=h).status_code == 200
    assert client.patch(url, json={"status": "arquivada"}, headers=h).status_code == 200
    # Filha não reativa enquanto o pai estiver arquivado.
    assert client.patch(child_url, json={"status": "ativa"}, headers=h).status_code == 409


def test_audit_records_pricing_changes(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    _, _, h_b = _admin(client, make_clinic)
    table = _base_table(client, h)
    tid = table["id"]
    client.patch(f"/precificacao/tabelas/{tid}", json={"description": "d"}, headers=h)
    draft = client.post(f"/precificacao/tabelas/{tid}/versoes", headers=h).json()
    client.post("/precificacao/snapshots", json={"procedure_code": "PROFILAXIA"}, headers=h)
    aid = client.get("/precificacao/atribuicoes", headers=h).json()[0]["id"]
    client.delete(f"/precificacao/atribuicoes/{aid}", headers=h)

    logs = client.get("/auditoria", headers=h).json()
    assert {
        "precificacao.tabela_criada",
        "precificacao.tabela_alterada",
        "precificacao.itens_substituidos",
        "precificacao.versao_publicada",
        "precificacao.versao_criada",
        "precificacao.atribuicao_criada",
        "precificacao.atribuicao_removida",
        "precificacao.snapshot_criado",
    } <= {r["action"] for r in logs}
    by_action = {r["action"]: r for r in logs}
    assert by_action["precificacao.tabela_criada"]["entity_id"] == tid
    assert by_action["precificacao.versao_criada"]["entity_id"] == draft["id"]

    # B não vê a auditoria de A.
    logs_b = client.get("/auditoria", headers=h_b).json()
    assert not any(r["action"].startswith("precificacao.") for r in logs_b)


# ---------- permissões ----------


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (Role.GESTOR, {"read", "resolve", "manage"}),
        (Role.DENTISTA, {"read", "resolve"}),
        (Role.RECEPCAO, {"read", "resolve"}),
        (Role.ASB, set()),
    ],
)
def test_roles(client, make_clinic, add_member, role, allowed):
    clinic, _, h = _admin(client, make_clinic)
    table = _base_table(client, h)
    tid = table["id"]
    v1 = client.get(f"/precificacao/tabelas/{tid}/versoes", headers=h).json()[0]
    snap = client.post(
        "/precificacao/snapshots", json={"procedure_code": "PROFILAXIA"}, headers=h
    ).json()
    aid = client.get("/precificacao/atribuicoes", headers=h).json()[0]["id"]
    _, hr = _member(client, add_member, clinic, role)

    calls = {
        "read": [
            ("get", "/precificacao/tabelas", None),
            ("get", f"/precificacao/tabelas/{tid}", None),
            ("get", f"/precificacao/tabelas/{tid}/versoes", None),
            ("get", f"/precificacao/tabelas/{tid}/versoes/{v1['id']}/itens", None),
            ("get", "/precificacao/atribuicoes", None),
            ("get", f"/precificacao/snapshots/{snap['id']}", None),
        ],
        "resolve": [
            ("post", "/precificacao/resolver", {"procedure_code": "PROFILAXIA"}),
            ("post", "/precificacao/snapshots", {"procedure_code": "PROFILAXIA"}),
        ],
        "manage": [
            ("patch", f"/precificacao/tabelas/{tid}", {"description": "x"}),
            ("post", f"/precificacao/tabelas/{tid}/versoes", None),
            ("delete", f"/precificacao/atribuicoes/{aid}", None),
            ("post", "/precificacao/tabelas", {"name": "Nova"}),
        ],
    }
    for group, group_calls in calls.items():
        for method, url, body in group_calls:
            kwargs = {"headers": hr} if body is None else {"headers": hr, "json": body}
            code = getattr(client, method)(url, **kwargs).status_code
            if group in allowed:
                assert code < 400, (role, method, url, code)
            else:
                assert code == 403, (role, method, url, code)


# ---------- isolamento entre clínicas ----------


def test_other_clinic_cannot_see_or_change(client, make_clinic, add_member):
    clinic_a, _, h_a = _admin(client, make_clinic)
    _, _, h_b = _admin(client, make_clinic)
    dentist_a, _ = add_member(clinic_a, Role.DENTISTA)
    table = _base_table(client, h_a)
    tid = table["id"]
    v1 = client.get(f"/precificacao/tabelas/{tid}/versoes", headers=h_a).json()[0]
    snap = client.post(
        "/precificacao/snapshots", json={"procedure_code": "PROFILAXIA"}, headers=h_a
    ).json()
    aid = client.get("/precificacao/atribuicoes", headers=h_a).json()[0]["id"]
    vurl = f"/precificacao/tabelas/{tid}/versoes/{v1['id']}"

    assert client.get("/precificacao/tabelas", headers=h_b).json() == []
    assert client.get("/precificacao/atribuicoes", headers=h_b).json() == []
    not_found = [
        client.get(f"/precificacao/tabelas/{tid}", headers=h_b),
        client.patch(f"/precificacao/tabelas/{tid}", json={"name": "x"}, headers=h_b),
        client.get(f"/precificacao/tabelas/{tid}/versoes", headers=h_b),
        client.post(f"/precificacao/tabelas/{tid}/versoes", headers=h_b),
        client.patch(vurl, json={"adjustment_pct": "5"}, headers=h_b),
        client.get(f"{vurl}/itens", headers=h_b),
        _put_items(client, h_b, table, v1, BASE_ITEMS),
        _publish(client, h_b, table, v1),
        _assign(client, h_b, table),
        client.delete(f"/precificacao/atribuicoes/{aid}", headers=h_b),
        client.get(f"/precificacao/snapshots/{snap['id']}", headers=h_b),
        # B não herda de tabela de A.
        client.post(
            "/precificacao/tabelas",
            json={"name": "Filha", "parent_table_id": tid, "adjustment_pct": "10"},
            headers=h_b,
        ),
    ]
    assert [r.status_code for r in not_found] == [404] * len(not_found)

    # Resolução em B não usa nem cita tabelas de A.
    resp = _resolve(client, h_b, "PROFILAXIA")
    assert resp.status_code == 404 and resp.json()["trace"] == []
    # B não congela preço citando dentista de A (aqui B nem tem tabela, então 404).
    snap_b = client.post(
        "/precificacao/snapshots",
        json={"procedure_code": "PROFILAXIA", "dentist_id": str(dentist_a.id)},
        headers=h_b,
    )
    assert snap_b.status_code == 404

    # A continua intacta.
    assert client.get(f"/precificacao/tabelas/{tid}", headers=h_a).json()["name"] == "Tabela Base"
    assert len(client.get("/precificacao/atribuicoes", headers=h_a).json()) == 1


def test_snapshot_rejects_dentist_from_other_clinic(client, make_clinic):
    _, _, h = _admin(client, make_clinic)
    _, outsider, _ = make_clinic(role=Role.DENTISTA)
    _base_table(client, h)
    resp = client.post(
        "/precificacao/snapshots",
        json={"procedure_code": "PROFILAXIA", "dentist_id": str(outsider.id)},
        headers=h,
    )
    assert resp.status_code == 409


def _row(table_name, clinic_id, table_id, version_id):
    """Uma linha da tabela indicada, apontando para registros (tabela/versão) da clínica A."""
    if table_name == "price_tables":
        return PriceTable(clinic_id=clinic_id, name="x", parent_table_id=table_id)
    if table_name == "price_table_versions":
        return PriceTableVersion(clinic_id=clinic_id, table_id=table_id, version=99)
    if table_name == "price_items":
        return PriceItem(
            clinic_id=clinic_id,
            version_id=version_id,
            procedure_code="X",
            description="X",
            price=Decimal("1.00"),
        )
    if table_name == "price_assignments":
        return PriceAssignment(
            clinic_id=clinic_id, table_id=table_id, scope_type=ScopeType.CLINICA, priority=1
        )
    return PriceSnapshot(
        clinic_id=clinic_id,
        procedure_code="X",
        description="X",
        price=Decimal("1.00"),
        table_id=table_id,
        version_id=version_id,
        effective_on=today(),
        trace=[],
    )


TENANT_TABLES = [
    ("price_tables", "fk_price_tables_parent_same_clinic"),
    ("price_table_versions", "fk_price_table_versions_table_same_clinic"),
    ("price_items", "fk_price_items_version_same_clinic"),
    ("price_assignments", "fk_price_assignments_table_same_clinic"),
    ("price_snapshots", "fk_price_snapshots_(table|version)_same_clinic"),
]


@pytest.fixture
def two_clinics_with_data(client, make_clinic):
    clinic_a, _, h_a = _admin(client, make_clinic)
    clinic_b, _, _ = make_clinic()
    table = _base_table(client, h_a)
    v1 = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h_a).json()[0]
    client.post("/precificacao/snapshots", json={"procedure_code": "PROFILAXIA"}, headers=h_a)
    return clinic_a, clinic_b, uuid.UUID(table["id"]), uuid.UUID(v1["id"])


@pytest.mark.parametrize(("table_name", "fk_name"), TENANT_TABLES)
def test_rls_and_composite_fk_block_cross_clinic_rows(two_clinics_with_data, table_name, fk_name):
    clinic_a, clinic_b, a_table, a_version = two_clinics_with_data
    model = type(_row(table_name, clinic_b.id, a_table, a_version))

    # A tem dados nesta tabela; B não enxerga nenhum.
    with tenant_session(clinic_a.id) as s:
        assert s.scalars(select(model)).all() != []
    with tenant_session(clinic_b.id) as s:
        assert s.scalars(select(model)).all() == []

    # Com o próprio clinic_id, B não consegue apontar para registros de A: a FK composta exige
    # a mesma clínica, e a checagem de FK não passa pelo RLS.
    with tenant_session(clinic_b.id) as s:
        s.add(_row(table_name, clinic_b.id, a_table, a_version))
        with pytest.raises(IntegrityError, match=fk_name):
            s.commit()

    # Com o clinic_id de A, o RLS (WITH CHECK) barra a gravação.
    with tenant_session(clinic_b.id) as s:
        s.add(_row(table_name, clinic_a.id, a_table, a_version))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.commit()


def test_snapshots_are_append_only(client, make_clinic):
    clinic, _, h = _admin(client, make_clinic)
    _base_table(client, h)
    client.post("/precificacao/snapshots", json={"procedure_code": "PROFILAXIA"}, headers=h)
    for sql in (
        "UPDATE price_snapshots SET price = 0",
        "DELETE FROM price_snapshots",
        "TRUNCATE price_snapshots",
    ):
        with tenant_session(clinic.id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))
