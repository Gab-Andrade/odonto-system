"""Precificação por custo: fichas técnicas, variáveis, tabelas calculadas e isolamento.

Cenário (valores conferidos à mão):
- custo_hora = 20000 / 160 = 125
- REST (60 min): resina 2 g × 3,20 + luva 1 × 0,80 = 7,20
  preço = (7,20 + 125 + 100) / (1 − 0,30) = 331,714... → 331,71
- PROF (30 min): luva 1 × 0,80 = 0,80
  preço = (0,80 + 62,50 + 50) / 0,70 = 161,857... → 161,86
- REST com pró-labore do dentista = 200: (7,20 + 125 + 200) / 0,70 = 474,571... → 474,57
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.precificacao.models import CostSheet, CostSheetItem, PricingVariable

pytestmark = pytest.mark.integration

CLINIC_VARS = {
    "custos_fixos_mensais": "20000",
    "horas_produtivas_mes": "160",
    "pro_labore_hora": "100",
    "impostos_pct": "6",
    "taxa_cartao_pct": "4",
    "margem_pct": "20",
}


def _admin(client, make_clinic):
    clinic, user, pw = make_clinic(role=Role.ADMIN)
    return clinic, _auth(_login(client, user.email, pw).json()["access_token"])


def _member(client, add_member, clinic, role):
    user, pw = add_member(clinic, role)
    return user, _auth(_login(client, user.email, pw).json()["access_token"])


def _material(client, h, name, unit, cost):
    resp = client.post(
        "/estoque/materiais", json={"name": name, "unit": unit, "unit_cost": cost}, headers=h
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _setup_costs(client, h):
    resina = _material(client, h, "Resina", "g", "3.20")
    luva = _material(client, h, "Luva", "par", "0.80")
    for code, desc, minutes, items in [
        ("REST", "Restauração", 60, [(resina, "2"), (luva, "1")]),
        ("PROF", "Profilaxia", 30, [(luva, "1")]),
    ]:
        resp = client.post(
            "/precificacao/fichas",
            json={
                "procedure_code": code,
                "description": desc,
                "duration_minutes": minutes,
                "items": [{"material_id": m, "quantity": q} for m, q in items],
            },
            headers=h,
        )
        assert resp.status_code == 201, resp.text
    for key, value in CLINIC_VARS.items():
        resp = client.put("/precificacao/variaveis", json={"key": key, "value": value}, headers=h)
        assert resp.status_code == 200, resp.text
    return {"resina": resina, "luva": luva}


def _calc_table(client, h, name="Calculada", **extra):
    resp = client.post(
        "/precificacao/tabelas", json={"name": name, "kind": "calculada", **extra}, headers=h
    )
    assert resp.status_code == 201, resp.text
    table = resp.json()
    draft = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()[0]
    return table, draft


def _vurl(table, version):
    return f"/precificacao/tabelas/{table['id']}/versoes/{version['id']}"


def _items(client, h, table, version):
    return {
        i["procedure_code"]: i
        for i in client.get(f"{_vurl(table, version)}/itens", headers=h).json()
    }


# ---------- fluxo ----------


def test_recalculate_publish_and_resolve(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    assert table["kind"] == "calculada"
    formula = client.get(f"{_vurl(table, draft)}/formula", headers=h).json()
    assert formula[-1]["nome"] == "preco"

    # Publicar sem recalcular é bloqueado.
    assert client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h).status_code == 409

    resp = client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["calculados"] == 2 and report["erros"] == []
    assert report["versao"]["calculated_at"] is not None

    items = _items(client, h, table, draft)
    assert items["REST"]["price"] == "331.71"
    assert items["PROF"]["price"] == "161.86"
    assert "calc_trace" not in items["REST"]  # custos não saem na listagem comum

    calc = client.get(f"{_vurl(table, draft)}/itens/{items['REST']['id']}/calculo", headers=h)
    trace = calc.json()["calc_trace"]
    assert trace["entradas"]["custo_materiais"] == {"valor": "7.2", "origem": "ficha técnica"}
    assert trace["entradas"]["margem_pct"] == {"valor": "20", "origem": "clínica"}
    assert [m["subtotal"] for m in trace["materiais"]] == ["6.40", "0.80"]
    assert trace["passos"][0] == {
        "nome": "custo_hora",
        "expressao": "custos_fixos_mensais / horas_produtivas_mes",
        "valor": "125",
    }

    assert client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h).status_code == 200
    client.post(
        "/precificacao/atribuicoes",
        json={"table_id": table["id"], "scope_type": "clinica"},
        headers=h,
    )
    resolved = client.post("/precificacao/resolver", json={"procedure_code": "REST"}, headers=h)
    assert resolved.json()["price"] == "331.71"


def test_dentist_variables_override_clinic(client, make_clinic, add_member):
    clinic, h = _admin(client, make_clinic)
    dentist, _ = _member(client, add_member, clinic, Role.DENTISTA)
    _setup_costs(client, h)
    client.put(
        "/precificacao/variaveis",
        json={"key": "pro_labore_hora", "value": "200", "dentist_id": str(dentist.id)},
        headers=h,
    )
    table, draft = _calc_table(client, h, "Dr. X", calc_dentist_id=str(dentist.id))
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    items = _items(client, h, table, draft)
    assert items["REST"]["price"] == "474.57"

    item_id = items["REST"]["id"]
    trace = client.get(f"{_vurl(table, draft)}/itens/{item_id}/calculo", headers=h).json()
    assert trace["calc_trace"]["entradas"]["pro_labore_hora"]["origem"] == "dentista"

    # A tabela da clínica continua usando o valor padrão.
    clinic_table, clinic_draft = _calc_table(client, h, "Clínica")
    client.post(f"{_vurl(clinic_table, clinic_draft)}/recalcular", headers=h)
    assert _items(client, h, clinic_table, clinic_draft)["REST"]["price"] == "331.71"


def test_try_formula_without_saving(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    resp = client.post(
        "/precificacao/formulas/testar",
        json={
            "procedure_code": "PROF",
            "formula": [
                {"nome": "base", "expressao": "custo_materiais + tempo_minutos"},
                {"nome": "preco", "expressao": "max(base * 2, 100)"},
            ],
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == "100.00"  # (0,80 + 30) × 2 = 61,60 → mínimo 100

    default = client.post(
        "/precificacao/formulas/testar", json={"procedure_code": "PROF"}, headers=h
    )
    assert default.json()["price"] == "161.86"

    bad = client.post(
        "/precificacao/formulas/testar",
        json={
            "procedure_code": "PROF",
            "formula": [{"nome": "preco", "expressao": "__import__('os')"}],
        },
        headers=h,
    )
    assert bad.status_code == 409


def test_missing_variables_and_formula_change_require_recalc(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    variables = client.get("/precificacao/variaveis", headers=h).json()
    margem = next(v for v in variables if v["key"] == "margem_pct")
    assert client.delete(f"/precificacao/variaveis/{margem['id']}", headers=h).status_code == 204

    table, draft = _calc_table(client, h)
    resp = client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    assert resp.status_code == 409 and "margem_pct" in resp.json()["detail"]

    client.put("/precificacao/variaveis", json={"key": "margem_pct", "value": "20"}, headers=h)
    assert client.post(f"{_vurl(table, draft)}/recalcular", headers=h).status_code == 200

    # Mudar a fórmula invalida o cálculo anterior.
    new_formula = [{"nome": "preco", "expressao": "custo_materiais * 10"}]
    patched = client.patch(_vurl(table, draft), json={"formula": new_formula}, headers=h)
    assert patched.status_code == 200 and patched.json()["calculated_at"] is None
    assert client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h).status_code == 409
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    assert _items(client, h, table, draft)["REST"]["price"] == "72.00"


def test_published_price_is_frozen_until_next_version(client, make_clinic):
    _, h = _admin(client, make_clinic)
    ids = _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h)
    client.post(
        "/precificacao/atribuicoes",
        json={"table_id": table["id"], "scope_type": "clinica"},
        headers=h,
    )

    client.patch(f"/estoque/materiais/{ids['resina']}", json={"unit_cost": "10"}, headers=h)
    resolve = {"procedure_code": "REST"}
    assert (
        client.post("/precificacao/resolver", json=resolve, headers=h).json()["price"] == "331.71"
    )

    v2 = client.post(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()
    assert v2["calculated_at"] is not None  # copiada da v1, mas ainda com os custos antigos
    client.post(f"{_vurl(table, v2)}/recalcular", headers=h)
    # (2 × 10 + 0,80 + 125 + 100) / 0,70 = 351,142... → 351,14
    assert _items(client, h, table, v2)["REST"]["price"] == "351.14"


def test_calculated_table_rejects_manual_items_import_and_parent(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    manual = [{"procedure_code": "X", "description": "X", "price": "1"}]
    assert (
        client.put(f"{_vurl(table, draft)}/itens", json={"items": manual}, headers=h).status_code
        == 409
    )
    up = client.post(
        "/precificacao/importacoes",
        files={"arquivo": ("t.csv", b"c;d;p\nX;X;1\n", "text/csv")},
        data={"table_id": table["id"]},
        headers=h,
    )
    assert up.status_code == 409
    base = client.post("/precificacao/tabelas", json={"name": "Base"}, headers=h).json()
    with_parent = client.post(
        "/precificacao/tabelas",
        json={"name": "Y", "kind": "calculada", "parent_table_id": base["id"]},
        headers=h,
    )
    assert with_parent.status_code == 409
    # E uma tabela fixa não aceita fórmula.
    fixed_draft = client.get(f"/precificacao/tabelas/{base['id']}/versoes", headers=h).json()[0]
    resp = client.patch(
        _vurl(base, fixed_draft), json={"formula": [{"nome": "preco", "expressao": "1"}]}, headers=h
    )
    assert resp.status_code == 409


def test_sheet_validation(client, make_clinic):
    _, h = _admin(client, make_clinic)
    ids = _setup_costs(client, h)
    base = {"procedure_code": "REST", "description": "x", "duration_minutes": 10, "items": []}
    assert client.post("/precificacao/fichas", json=base, headers=h).status_code == 409  # já existe
    unknown = {
        **base,
        "procedure_code": "NOVO",
        "items": [{"material_id": str(uuid.uuid4()), "quantity": "1"}],
    }
    assert client.post("/precificacao/fichas", json=unknown, headers=h).status_code == 404
    client.patch(f"/estoque/materiais/{ids['luva']}", json={"active": False}, headers=h)
    inactive = {
        **base,
        "procedure_code": "NOVO",
        "items": [{"material_id": ids["luva"], "quantity": "1"}],
    }
    assert client.post("/precificacao/fichas", json=inactive, headers=h).status_code == 409
    reserved = client.put(
        "/precificacao/variaveis", json={"key": "tempo_horas", "value": "1"}, headers=h
    )
    assert reserved.status_code == 409


def test_audit(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    actions = {r["action"] for r in client.get("/auditoria?limit=100", headers=h).json()}
    assert {
        "precificacao.ficha_criada",
        "precificacao.variavel_definida",
        "precificacao.versao_recalculada",
    } <= actions


# ---------- permissões ----------


@pytest.mark.parametrize("role", [Role.DENTISTA, Role.RECEPCAO, Role.ASB])
def test_costs_are_managers_only(client, make_clinic, add_member, role):
    clinic, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    item = next(iter(_items(client, h, table, draft).values()))
    _, hr = _member(client, add_member, clinic, role)

    for method, url, body in [
        ("get", "/precificacao/fichas", None),
        ("get", "/precificacao/variaveis", None),
        ("get", "/precificacao/formulas/padrao", None),
        ("post", "/precificacao/formulas/testar", {"procedure_code": "REST"}),
        ("get", f"{_vurl(table, draft)}/formula", None),
        ("get", f"{_vurl(table, draft)}/itens/{item['id']}/calculo", None),
        ("post", f"{_vurl(table, draft)}/recalcular", None),
        ("put", "/precificacao/variaveis", {"key": "x", "value": "1"}),
    ]:
        kwargs = {"headers": hr} if body is None else {"headers": hr, "json": body}
        assert getattr(client, method)(url, **kwargs).status_code == 403, (role, url)


# ---------- isolamento entre clínicas ----------


def test_other_clinic_cannot_use_or_see_costs(client, make_clinic):
    clinic_a, h_a = _admin(client, make_clinic)
    clinic_b, h_b = _admin(client, make_clinic)
    ids = _setup_costs(client, h_a)
    sheet = client.get("/precificacao/fichas", headers=h_a).json()[0]
    variable = client.get("/precificacao/variaveis", headers=h_a).json()[0]

    assert client.get("/precificacao/fichas", headers=h_b).json() == []
    assert client.get("/precificacao/variaveis", headers=h_b).json() == []
    assert client.get(f"/precificacao/fichas/{sheet['id']}", headers=h_b).status_code == 404
    assert (
        client.delete(f"/precificacao/variaveis/{variable['id']}", headers=h_b).status_code == 404
    )
    # B não usa material de A na própria ficha.
    steal = {
        "procedure_code": "X",
        "description": "x",
        "duration_minutes": 10,
        "items": [{"material_id": ids["resina"], "quantity": "1"}],
    }
    assert client.post("/precificacao/fichas", json=steal, headers=h_b).status_code == 404
    # B não calcula com as fichas/variáveis de A.
    assert (
        client.post(
            "/precificacao/formulas/testar", json={"procedure_code": "REST"}, headers=h_b
        ).status_code
        == 404
    )

    for model in (CostSheet, CostSheetItem, PricingVariable):
        with tenant_session(clinic_b.id) as s:
            assert s.scalars(select(model)).all() == []

    # FK composta: mesmo com o próprio clinic_id, B não aponta para material de A.
    with tenant_session(clinic_b.id) as s:
        own = CostSheet(
            clinic_id=clinic_b.id, procedure_code="B1", description="b", duration_minutes=5
        )
        s.add(own)
        s.flush()
        s.add(
            CostSheetItem(
                clinic_id=clinic_b.id,
                sheet_id=own.id,
                material_id=uuid.UUID(ids["resina"]),
                quantity=1,
            )
        )
        with pytest.raises(IntegrityError, match="fk_cost_sheet_items_material_same_clinic"):
            s.commit()
    with tenant_session(clinic_b.id) as s:
        s.add(PricingVariable(clinic_id=clinic_a.id, key="x", value=1))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.commit()


# ---------- revisão: insumos defasados, dentistas e isolamento das rotas de custo ----------


@pytest.mark.parametrize("change", ["material", "variavel", "ficha"])
def test_publish_blocked_when_inputs_changed_after_recalc(client, make_clinic, change):
    _, h = _admin(client, make_clinic)
    ids = _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)

    if change == "material":
        client.patch(f"/estoque/materiais/{ids['luva']}", json={"unit_cost": "1.00"}, headers=h)
    elif change == "variavel":
        client.put("/precificacao/variaveis", json={"key": "margem_pct", "value": "25"}, headers=h)
    else:
        sheet = next(
            s
            for s in client.get("/precificacao/fichas", headers=h).json()
            if s["procedure_code"] == "PROF"
        )
        body = {
            "procedure_code": "PROF",
            "description": "Profilaxia",
            "duration_minutes": 45,
            "items": sheet["items"],
        }
        assert (
            client.put(f"/precificacao/fichas/{sheet['id']}", json=body, headers=h).status_code
            == 200
        )

    resp = client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h)
    assert resp.status_code == 409 and "Recalcule" in resp.json()["detail"]
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    assert client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h).status_code == 200


def test_new_draft_of_calculated_table_detects_stale_costs(client, make_clinic):
    _, h = _admin(client, make_clinic)
    ids = _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h)
    client.post(f"{_vurl(table, draft)}/publicar", json={}, headers=h)
    client.patch(f"/estoque/materiais/{ids['resina']}", json={"unit_cost": "5"}, headers=h)
    v2 = client.post(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    resp = client.post(f"{_vurl(table, v2)}/publicar", json={"valid_from": tomorrow}, headers=h)
    assert resp.status_code == 409


def test_dentist_from_other_clinic_rejected(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _, outsider, _ = make_clinic(role=Role.DENTISTA)
    _setup_costs(client, h)
    other = str(outsider.id)
    assert (
        client.put(
            "/precificacao/variaveis",
            json={"key": "pro_labore_hora", "value": "1", "dentist_id": other},
            headers=h,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/precificacao/formulas/testar",
            json={"procedure_code": "REST", "dentist_id": other},
            headers=h,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/precificacao/tabelas",
            json={"name": "X", "kind": "calculada", "calc_dentist_id": other},
            headers=h,
        ).status_code
        == 409
    )


def test_recalc_rejects_dentist_who_left(client, make_clinic, add_member, db_session):
    from app.modules.identidade.models import ClinicMembership

    clinic, h = _admin(client, make_clinic)
    dentist, _ = _member(client, add_member, clinic, Role.DENTISTA)
    _setup_costs(client, h)
    table, draft = _calc_table(client, h, "Dr. Y", calc_dentist_id=str(dentist.id))
    membership = db_session.query(ClinicMembership).filter_by(user_id=dentist.id).one()
    membership.active = False
    db_session.commit()
    assert client.post(f"{_vurl(table, draft)}/recalcular", headers=h).status_code == 409


def test_inactive_material_still_costs_existing_sheets(client, make_clinic):
    _, h = _admin(client, make_clinic)
    ids = _setup_costs(client, h)
    client.patch(f"/estoque/materiais/{ids['luva']}", json={"active": False}, headers=h)
    table, draft = _calc_table(client, h)
    report = client.post(f"{_vurl(table, draft)}/recalcular", headers=h).json()
    assert report["calculados"] == 2
    assert _items(client, h, table, draft)["PROF"]["price"] == "161.86"


def test_other_clinic_cannot_read_formula_or_item_calculation(client, make_clinic):
    _, h_a = _admin(client, make_clinic)
    _, h_b = _admin(client, make_clinic)
    _setup_costs(client, h_a)
    table, draft = _calc_table(client, h_a)
    client.post(f"{_vurl(table, draft)}/recalcular", headers=h_a)
    item = next(iter(_items(client, h_a, table, draft).values()))
    assert client.get(f"{_vurl(table, draft)}/formula", headers=h_b).status_code == 404
    assert (
        client.get(f"{_vurl(table, draft)}/itens/{item['id']}/calculo", headers=h_b).status_code
        == 404
    )
    assert client.post(f"{_vurl(table, draft)}/recalcular", headers=h_b).status_code == 404
    patch = client.patch(
        _vurl(table, draft), json={"formula": [{"nome": "preco", "expressao": "0"}]}, headers=h_b
    )
    assert patch.status_code == 404


def test_formula_errors_per_procedure_do_not_abort_recalc(client, make_clinic):
    _, h = _admin(client, make_clinic)
    _setup_costs(client, h)
    table, draft = _calc_table(client, h)
    # REST tem custo_materiais 7,20; PROF tem 0,80 → divisão por zero só em PROF.
    formula = [{"nome": "preco", "expressao": "100 / (custo_materiais - 0.8)"}]
    client.patch(_vurl(table, draft), json={"formula": formula}, headers=h)
    report = client.post(f"{_vurl(table, draft)}/recalcular", headers=h).json()
    assert report["calculados"] == 1
    assert report["erros"] == [{"procedimento": "PROF", "erro": "preco: Divisão por zero."}]
