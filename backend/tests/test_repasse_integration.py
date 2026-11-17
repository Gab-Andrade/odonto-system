"""Repasse: regras, prévia e fechamento acumulado sobre o recebido, papéis, banco e
isolamento entre clínicas."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_tratamento_integration import _decide, _issue, _plan, _setup

from app.core.db import tenant_session
from app.modules.financeiro.service import today
from app.modules.repasse.models import CommissionLine, CommissionSettlement

pytestmark = pytest.mark.integration


def _post(client, ctx, url, body, who="admin", expect=201):
    resp = client.post(url, json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _performed_plan(client, ctx):
    """Restauração (200) + profilaxia (120), aprovadas, realizadas pelo dentista e
    parceladas em 2 × 160."""
    plan = _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "RESTAURACAO"},
                                                   {"procedure_code": "PROFILAXIA"}]))  # fmt: skip
    _decide(client, ctx, plan, [i["id"] for i in plan["items"]])
    enc = _post(client, ctx, "/prontuario/atendimentos", {"patient_id": ctx["patient"]}, "dent")
    for item in plan["items"]:
        _post(client, ctx, f"/tratamento/itens/{item['id']}/realizar",
              {"encounter_id": enc["id"]}, "dent", 200)  # fmt: skip
    rows = _post(client, ctx, f"/financeiro/planos/{plan['id']}/parcelamento",
                 {"installments": 2}, "recep")  # fmt: skip
    return plan, rows


def _rules(client, ctx):
    dent = ctx["ids"]["dent"]
    _post(client, ctx, "/repasse/regras",
          {"dentist_id": dent, "value": "40", "deduct_card_fee": True})  # fmt: skip
    _post(client, ctx, "/repasse/regras",
          {"dentist_id": dent, "procedure_code": "PROFILAXIA", "kind": "fixo", "value": "50"},
          who="gestor")  # fmt: skip


def _preview(client, ctx, until, who="admin", dentist="dent", expect=200):
    params = {"ate": str(until)}
    if dentist:
        params["dentista_id"] = ctx["ids"][dentist]
    resp = client.get("/repasse/previa", params=params, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def test_commission_on_received_and_cumulative(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _rules(client, ctx)
    _, rows = _performed_plan(client, ctx)

    # Nada pago: nada a repassar.
    assert _preview(client, ctx, today())["total"] == "0.00"

    # Metade paga no crédito (taxa 5%).
    _post(client, ctx, f"/financeiro/receber/{rows[0]['id']}/pagamentos",
          {"amount": "160.00", "method": "credito", "fee_pct": "5"}, "recep")  # fmt: skip
    prev = _preview(client, ctx, today())
    lines = {line["procedure_code"]: line for line in prev["lines"]}
    assert lines["RESTAURACAO"]["base_amount"] == "100.00"
    assert lines["RESTAURACAO"]["fee_deduction"] == "5.00"
    assert lines["RESTAURACAO"]["commission"] == "38.00"  # (100 − 5) × 40%
    assert lines["PROFILAXIA"]["commission"] == "25.00"  # fixo 50 × metade paga
    assert prev["total"] == "63.00" and prev["missing_rule"] == []

    closed = _post(client, ctx, "/repasse/fechamentos",
                   {"dentist_id": ctx["ids"]["dent"], "period_end": str(today())})  # fmt: skip
    assert closed["total"] == "63.00" and len(closed["lines"]) == 2
    _post(client, ctx, "/repasse/fechamentos",
          {"dentist_id": ctx["ids"]["dent"], "period_end": str(today())}, expect=409)  # fmt: skip
    _post(client, ctx, "/repasse/fechamentos",
          {"dentist_id": ctx["ids"]["dent"], "period_end": str(today() + timedelta(days=1))},
          expect=409)  # fmt: skip  # futuro

    # Segunda parcela paga: o próximo fechamento leva só a diferença.
    _post(client, ctx, f"/financeiro/receber/{rows[1]['id']}/pagamentos",
          {"amount": "160.00", "method": "pix"}, "recep")  # fmt: skip
    nxt = _preview(client, ctx, today() + timedelta(days=1))
    lines = {line["procedure_code"]: line for line in nxt["lines"]}
    assert lines["RESTAURACAO"]["base_amount"] == "100.00"
    assert lines["RESTAURACAO"]["fee_deduction"] == "2.50"  # taxa média do plano: 8 / 320
    assert lines["RESTAURACAO"]["commission"] == "39.00"
    assert lines["PROFILAXIA"]["commission"] == "25.00"
    assert nxt["period_start"] == str(today() + timedelta(days=1))

    # O dentista vê o próprio repasse, não o de outro.
    mine = client.get("/repasse/fechamentos", headers=ctx["h"]["dent"]).json()
    assert [s["id"] for s in mine] == [closed["id"]]
    detail = client.get(f"/repasse/fechamentos/{closed['id']}", headers=ctx["h"]["dent"])
    assert detail.status_code == 200 and detail.json()["total"] == "63.00"
    assert client.get(f"/repasse/fechamentos/{closed['id']}",
                      headers=ctx["h"]["dent2"]).status_code == 403  # fmt: skip
    _preview(client, ctx, today(), who="dent2", dentist="dent", expect=403)
    other = client.get("/repasse/fechamentos", params={"dentista_id": ctx["ids"]["dent"]},
                       headers=ctx["h"]["dent2"])  # fmt: skip
    assert other.status_code == 403
    assert client.get("/repasse/fechamentos", headers=ctx["h"]["dent2"]).json() == []
    _preview(client, ctx, today(), dentist="recep", expect=409)  # não é dentista
    assert _preview(client, ctx, today(), who="dent2", dentist=None)["lines"] == []


def test_missing_rule_and_roles(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _, rows = _performed_plan(client, ctx)
    _post(client, ctx, f"/financeiro/receber/{rows[0]['id']}/pagamentos",
          {"amount": "160.00", "method": "pix"}, "recep")  # fmt: skip
    prev = _preview(client, ctx, today())
    assert prev["lines"] == [] and sorted(prev["missing_rule"]) == ["PROFILAXIA", "RESTAURACAO"]

    for who in ("dent", "asb", "recep"):
        _post(client, ctx, "/repasse/regras", {"dentist_id": ctx["ids"]["dent"], "value": "10"},
              who=who, expect=403)  # fmt: skip
    for who in ("asb", "recep"):
        assert client.get("/repasse/fechamentos", headers=ctx["h"][who]).status_code == 403
    _post(client, ctx, "/repasse/regras", {"dentist_id": ctx["ids"]["recep"], "value": "10"},
          expect=409)  # recepção não é dentista  # fmt: skip
    _post(client, ctx, "/repasse/regras", {"dentist_id": ctx["ids"]["dent"], "value": "101"},
          expect=409)  # fmt: skip


def test_database_guards_and_isolation(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    _rules(client, a)
    _, rows = _performed_plan(client, a)
    _post(client, a, f"/financeiro/receber/{rows[0]['id']}/pagamentos",
          {"amount": "160.00", "method": "pix"}, "recep")  # fmt: skip
    closed = _post(client, a, "/repasse/fechamentos",
                   {"dentist_id": a["ids"]["dent"], "period_end": str(today())})  # fmt: skip

    for sql in (
        "UPDATE commission_lines SET commission = 0",
        "DELETE FROM commission_lines",
        "UPDATE commission_settlements SET total = 0",
        "DELETE FROM commission_rules",
    ):
        with tenant_session(a["clinic"].id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))

    hb = b["h"]["admin"]
    assert client.get("/repasse/fechamentos", headers=hb).json() == []
    assert client.get(f"/repasse/fechamentos/{closed['id']}", headers=hb).status_code == 404
    _post(client, b, "/repasse/regras", {"dentist_id": a["ids"]["dent"], "value": "10"},
          expect=409)  # dentista de outra clínica  # fmt: skip
    with tenant_session(b["clinic"].id) as s:
        for model in (CommissionSettlement, CommissionLine):
            assert s.scalar(select(func.count()).select_from(model)) == 0
        s.add(CommissionSettlement(clinic_id=a["clinic"].id, dentist_id=uuid.UUID(a["ids"]["dent"]),
                                   period_end=today(), total=0))  # fmt: skip
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
