"""Painel do gestor: visão geral da clínica, "meu desempenho", papéis e isolamento."""

from datetime import timedelta

import pytest
from test_tratamento_integration import _decide, _issue, _plan, _setup

from app.modules.financeiro.service import today
from app.modules.painel.service import day_bounds

pytestmark = pytest.mark.integration


def _post(client, ctx, url, body, who="admin", expect=201):
    resp = client.post(url, json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _scenario(client, ctx):
    """Hoje: uma consulta confirmada e uma agendada; um orçamento (320) aprovado e
    realizado pelo dentista, parcelado 2 × 160 com a 1ª paga no crédito (taxa 5%); um
    orçamento emitido aguardando; uma conta a pagar vencida."""
    # Horários fixos do dia local (não relativos a agora: perto da meia-noite cairiam em
    # outro dia no fuso da clínica).
    midnight = day_bounds(today())[0]
    for hours, confirm in ((10, True), (15, False)):
        start = midnight + timedelta(hours=hours)
        appt = _post(client, ctx, "/agenda/agendamentos", {
            "patient_id": ctx["patient"], "dentist_id": ctx["ids"]["dent"],
            "starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=30)).isoformat(),
        }, "recep")  # fmt: skip
        if confirm:
            _post(client, ctx, f"/agenda/agendamentos/{appt['id']}/status",
                  {"status": "confirmado"}, "recep", 200)  # fmt: skip
    plan = _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "RESTAURACAO"},
                                                   {"procedure_code": "PROFILAXIA"}]))  # fmt: skip
    _decide(client, ctx, plan, [i["id"] for i in plan["items"]])
    enc = _post(client, ctx, "/prontuario/atendimentos", {"patient_id": ctx["patient"]}, "dent")
    for item in plan["items"]:
        _post(client, ctx, f"/tratamento/itens/{item['id']}/realizar",
              {"encounter_id": enc["id"]}, "dent", 200)  # fmt: skip
    rows = _post(client, ctx, f"/financeiro/planos/{plan['id']}/parcelamento",
                 {"installments": 2, "first_due_date": str(today())}, "recep")  # fmt: skip
    _post(client, ctx, f"/financeiro/receber/{rows[0]['id']}/pagamentos",
          {"amount": "160.00", "method": "credito", "fee_pct": "5"}, "recep")  # fmt: skip
    _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "CANAL"}]))
    _post(client, ctx, "/financeiro/receber", {
        "patient_id": ctx["patient"], "description": "Avulsa vencida",
        "due_date": str(today() - timedelta(days=40)), "amount": "50.00",  # mês anterior
    }, "recep")  # fmt: skip
    _post(client, ctx, "/financeiro/pagar", {
        "supplier": "Dental Sul", "due_date": str(today() - timedelta(days=2)), "amount": "500.00",
    }, "gestor")  # fmt: skip


def test_overview_and_my_performance(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _scenario(client, ctx)

    resp = client.get("/painel/visao-geral", headers=ctx["h"]["gestor"])
    assert resp.status_code == 200, resp.text
    ov = resp.json()
    assert ov["agenda"]["total"] == 2
    assert (ov["agenda"]["confirmado"], ov["agenda"]["agendado"]) == (1, 1)
    assert ov["revenue"] == {"received": "160.00", "received_net": "152.00", "expected": "160.00"}
    assert ov["overdue"] == {"count": 1, "amount": "50.00"}
    assert (ov["payables"]["overdue_count"], ov["payables"]["overdue_amount"]) == (1, "500.00")
    assert ov["quotes"]["awaiting"] == 1 and ov["quotes"]["issued_in_month"] == 2
    assert ov["quotes"]["approved_in_month"] == 1
    assert ov["quotes"]["approved_value_in_month"] == "320.00"
    [prod] = ov["production"]
    assert prod["dentist_id"] == ctx["ids"]["dent"] and prod["procedures"] == 2
    assert prod["value"] == "320.00" and prod["dentist_name"]

    mine = client.get("/painel/meu-desempenho", headers=ctx["h"]["dent"])
    assert mine.status_code == 200, mine.text
    me = mine.json()
    assert me["agenda_today"]["total"] == 2 and me["encounters"] == 1
    assert me["production"]["value"] == "320.00" and me["last_settlement"] is None
    assert me["quotes"]["awaiting"] == 1  # o plano do CANAL, emitido e sem decisão

    other = client.get("/painel/meu-desempenho", headers=ctx["h"]["dent2"]).json()
    assert other["production"]["procedures"] == 0 and other["agenda_today"]["total"] == 0

    old = client.get("/painel/visao-geral", params={"mes": "2020-01"}, headers=ctx["h"]["admin"])
    assert old.json()["production"] == [] and old.json()["revenue"]["received"] == "0.00"
    bad = client.get("/painel/visao-geral", params={"mes": "2026-13"}, headers=ctx["h"]["admin"])
    assert bad.status_code == 422


def test_roles_and_isolation(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    _scenario(client, a)
    for who in ("dent", "asb", "recep"):
        assert client.get("/painel/visao-geral", headers=a["h"][who]).status_code == 403
    for who in ("gestor", "asb", "recep"):
        assert client.get("/painel/meu-desempenho", headers=a["h"][who]).status_code == 403

    ov = client.get("/painel/visao-geral", headers=b["h"]["admin"]).json()
    assert ov["agenda"]["total"] == 0 and ov["production"] == []
    assert ov["revenue"]["received"] == "0.00" and ov["payables"]["overdue_count"] == 0
