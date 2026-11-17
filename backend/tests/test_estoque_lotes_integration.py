"""Estoque por lote: entradas e custo médio, saídas, inventário, baixa automática pela
ficha técnica (FEFO) ao realizar o procedimento, rastreio por paciente, alertas, papéis,
banco e isolamento."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_tratamento_integration import _decide, _issue, _plan, _setup

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.modules.estoque.lotes_service import today
from app.modules.estoque.models import StockLot, StockMovement

pytestmark = pytest.mark.integration


def _post(client, ctx, url, body, who="asb", expect=201):
    resp = client.post(url, json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _material(client, ctx, name="Resina A2", min_quantity=None):
    body = {"name": name, "unit": "g", "unit_cost": "1.0000"}
    if min_quantity is not None:
        body["min_quantity"] = min_quantity
    return _post(client, ctx, "/estoque/materiais", body, who="admin")


def _entry(client, ctx, material, quantity, cost, expires=None, lot="L1", who="gestor",
           expect=201):  # fmt: skip
    body = {"material_id": material["id"], "quantity": str(quantity),
            "unit_cost": str(cost) if cost is not None else None,
            "lot_code": lot, "expires_on": str(expires) if expires else None}  # fmt: skip
    return _post(client, ctx, "/estoque/entradas", body, who, expect)


def _stock(client, ctx, who="dent", **params):
    resp = client.get("/estoque/saldos", params=params, headers=ctx["h"][who])
    assert resp.status_code == 200, resp.text
    return {m["name"]: m for m in resp.json()}


# ---------- entradas, saídas, inventário ----------


def test_entries_average_cost_exits_and_adjustment(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    resina = _material(client, ctx, min_quantity="6")
    soon = today() + timedelta(days=10)
    later = today() + timedelta(days=200)
    lot1 = _entry(client, ctx, resina, "10", "2.0000", expires=later, lot="A")
    assert lot1["balance"] == "10.0000" and lot1["unit_cost"] == "2.0000"
    _entry(client, ctx, resina, "30", "4.0000", expires=soon, lot="B")
    # ASB dá entrada sem custo (e não pode informá-lo); o custo médio não muda por isso.
    _entry(client, ctx, resina, "1", "9.0000", who="asb", expect=409)
    _entry(client, ctx, resina, "1", None, who="gestor", expect=409)

    # Custo médio ponderado vai para o material (usado pela precificação).
    got = client.get(f"/estoque/materiais/{resina['id']}", headers=ctx["h"]["admin"]).json()
    assert got["unit_cost"] == "3.5000"
    asb_lot = _entry(client, ctx, resina, "4", None, who="asb", lot="C")
    assert asb_lot["unit_cost"] is None  # ASB não vê custo
    got = client.get(f"/estoque/materiais/{resina['id']}", headers=ctx["h"]["admin"]).json()
    assert got["unit_cost"] == "3.5000"

    st = _stock(client, ctx)["Resina A2"]
    assert st["balance"] == "44.0000" and st["below_minimum"] is False
    assert [(lot["lot_code"], lot["expiry"]) for lot in st["lots"]] == [
        ("B", "vence_em_breve"),
        ("A", "ok"),
        ("C", "sem_validade"),
    ]
    _post(
        client, ctx, "/estoque/saidas", {"lot_id": asb_lot["id"], "quantity": "4", "reason": "Uso"}
    )

    # Saída manual e inventário.
    _post(client, ctx, "/estoque/saidas", {"lot_id": lot1["id"], "quantity": "11", "reason": "x"},
          expect=409)  # acima do saldo  # fmt: skip
    _post(client, ctx, "/estoque/saidas",
          {"lot_id": lot1["id"], "quantity": "4", "reason": "Perda"})  # fmt: skip
    adj = {"lot_id": lot1["id"], "counted_quantity": "5", "reason": "Inventário"}
    _post(client, ctx, "/estoque/ajustes", adj, who="asb", expect=403)
    moved = _post(client, ctx, "/estoque/ajustes", adj, who="gestor", expect=200)
    assert moved["quantity"] == "-1.0000"
    assert _post(client, ctx, "/estoque/ajustes", adj, who="gestor", expect=200) is None

    # Abaixo do mínimo aparece nos alertas.
    lot_b = _stock(client, ctx)["Resina A2"]["lots"][0]
    _post(
        client, ctx, "/estoque/saidas", {"lot_id": lot_b["id"], "quantity": "30", "reason": "Uso"}
    )
    alerts = _stock(client, ctx, somente_alertas=True)
    assert (
        alerts["Resina A2"]["below_minimum"] is True and alerts["Resina A2"]["balance"] == "5.0000"
    )

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"estoque.entrada", "estoque.saida", "estoque.ajuste"} <= actions


# ---------- baixa automática ----------


def test_perform_item_consumes_by_fefo_and_traces_patient(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    resina = _material(client, ctx)
    implante = _material(client, ctx, name="Implante 4x10")
    for name, body in (
        (
            "RESTAURACAO",
            [
                {"material_id": resina["id"], "quantity": "3"},
                {"material_id": implante["id"], "quantity": "1"},
            ],
        ),
    ):
        sheet = {"procedure_code": name, "description": "Restauração", "duration_minutes": 40,
                 "items": body}  # fmt: skip
        _post(client, ctx, "/precificacao/fichas", sheet, who="admin")
    near = today() + timedelta(days=5)
    far = today() + timedelta(days=300)
    _entry(client, ctx, resina, "2", "1", expires=near, lot="R-NEAR")
    _entry(client, ctx, resina, "10", "1", expires=far, lot="R-FAR")
    _entry(client, ctx, resina, "50", "1", expires=today() - timedelta(days=1), lot="R-OLD")
    # Implante sem estoque: o procedimento é registrado mesmo assim, com aviso.

    plan = _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "RESTAURACAO"}]))
    _decide(client, ctx, plan, [plan["items"][0]["id"]])
    enc = _post(client, ctx, "/prontuario/atendimentos", {"patient_id": ctx["patient"]}, who="dent")
    done = _post(client, ctx, f"/tratamento/itens/{plan['items'][0]['id']}/realizar",
                 {"encounter_id": enc["id"]}, who="dent", expect=200)  # fmt: skip
    assert done["items"][0]["status"] == "realizado"
    assert len(done["warnings"]) == 1 and "Implante 4x10" in done["warnings"][0]

    lots = {lot["lot_code"]: lot["balance"] for lot in _stock(client, ctx)["Resina A2"]["lots"]}
    assert lots == {"R-FAR": "9.0000", "R-OLD": "50.0000"}  # 2 do que vence antes + 1 do outro

    trace = client.get(f"/estoque/pacientes/{ctx['patient']}/rastreio", headers=ctx["h"]["dent"])
    assert trace.status_code == 200, trace.text
    assert sorted((t["lot_code"], t["quantity"]) for t in trace.json()) == [
        ("R-FAR", "-1.0000"),
        ("R-NEAR", "-2.0000"),
    ]
    assert client.get(f"/estoque/pacientes/{ctx['patient']}/rastreio",
                      headers=ctx["h"]["recep"]).status_code == 403  # fmt: skip


# ---------- papéis, banco e isolamento ----------


def test_roles_and_database_guards(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    resina = _material(client, ctx)
    _entry(client, ctx, resina, "1", None, who="dent", expect=403)
    _entry(client, ctx, resina, "1", None, who="recep", expect=403)
    lot = _entry(client, ctx, resina, "5", "2", who="gestor")
    assert lot["unit_cost"] == "2.0000"  # gestor vê custo
    assert client.get("/estoque/saldos", headers=ctx["h"]["recep"]).status_code == 403
    assert client.get("/estoque/movimentos", headers=ctx["h"]["asb"]).status_code == 403

    cid = ctx["clinic"].id
    for sql in ("UPDATE stock_movements SET quantity = 100", "DELETE FROM stock_movements",
                "DELETE FROM stock_lots"):  # fmt: skip
        with tenant_session(cid) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))
    with tenant_session(cid) as s:
        s.add(StockMovement(clinic_id=cid, lot_id=uuid.UUID(lot["id"]),
                            material_id=uuid.UUID(resina["id"]), kind="saida",
                            quantity=Decimal("-6"), reason="x"))  # fmt: skip
        with pytest.raises(IntegrityError, match="negativo"):
            s.flush()
    with tenant_session(cid) as s:
        row = s.get(StockLot, uuid.UUID(lot["id"]))
        row.unit_cost = Decimal("0.01")
        with pytest.raises(IntegrityError, match="custo"):
            s.flush()


def test_other_clinic_cannot_see_or_move(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    resina = _material(client, a)
    lot = _entry(client, a, resina, "5", "1")

    assert _stock(client, b) == {}
    _post(client, b, "/estoque/saidas", {"lot_id": lot["id"], "quantity": "1", "reason": "x"},
          expect=404)  # fmt: skip
    _entry(client, b, resina, "1", "1", expect=404)  # material de A
    assert client.get(f"/estoque/pacientes/{a['patient']}/rastreio",
                      headers=b["h"]["dent"]).status_code == 404  # fmt: skip

    with tenant_session(b["clinic"].id) as s:
        assert s.scalar(select(func.count()).select_from(StockLot)) == 0
        s.add(StockLot(clinic_id=b["clinic"].id, material_id=uuid.UUID(resina["id"]),
                       unit_cost=Decimal("1"), received_on=today()))  # fmt: skip
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        s.add(StockLot(clinic_id=a["clinic"].id, material_id=uuid.UUID(resina["id"]),
                       unit_cost=Decimal("1"), received_on=today()))  # fmt: skip
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()

    with tenant_session(b["clinic"].id) as s:
        assert s.scalar(select(func.count()).select_from(StockMovement)) == 0
        # B não movimenta o lote de A (FK composta)...
        s.add(StockMovement(clinic_id=b["clinic"].id, lot_id=uuid.UUID(lot["id"]),
                            material_id=uuid.UUID(resina["id"]), kind="entrada",
                            quantity=Decimal("1")))  # fmt: skip
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        # ...nem grava movimento com o clinic_id de A.
        s.add(StockMovement(clinic_id=a["clinic"].id, lot_id=uuid.UUID(lot["id"]),
                            material_id=uuid.UUID(resina["id"]), kind="entrada",
                            quantity=Decimal("1")))  # fmt: skip
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
    assert client.get("/estoque/movimentos", headers=b["h"]["admin"]).json() == []
    # Movimento com lote de outro material da mesma clínica é barrado.
    outro = _material(client, a, name="Anestésico")
    with tenant_session(a["clinic"].id) as s:
        s.add(StockMovement(clinic_id=a["clinic"].id, lot_id=uuid.UUID(lot["id"]),
                            material_id=uuid.UUID(outro["id"]), kind="entrada",
                            quantity=Decimal("1")))  # fmt: skip
        with pytest.raises(IntegrityError):
            s.flush()
