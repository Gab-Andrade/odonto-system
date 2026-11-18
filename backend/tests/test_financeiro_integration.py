"""Financeiro: parcelamento do orçamento, recebimentos e estorno, extrato, contas a pagar,
papéis, garantias no banco e isolamento entre clínicas."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login
from test_tratamento_integration import _decide, _issue, _plan, _setup

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.financeiro.models import Payable, Payment, Receivable
from app.modules.financeiro.service import today

pytestmark = pytest.mark.integration


def _approved_plan(client, ctx):
    """Orçamento aprovado: restauração (200) + profilaxia (120) = 320."""
    plan = _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "RESTAURACAO"},
                                                   {"procedure_code": "PROFILAXIA"}]))  # fmt: skip
    return _decide(client, ctx, plan, [i["id"] for i in plan["items"]])


def _post(client, ctx, url, body=None, who="recep", expect=201):
    resp = client.post(url, json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _installments(client, ctx, plan, expect=201, who="recep", **body):
    return _post(client, ctx, f"/financeiro/planos/{plan['id']}/parcelamento", body, who, expect)


def _pay(client, ctx, receivable, amount, expect=201, who="recep", **extra):
    body = {"amount": str(amount), "method": "pix", **extra}
    return _post(client, ctx, f"/financeiro/receber/{receivable['id']}/pagamentos", body, who,
                 expect)  # fmt: skip


# ---------- parcelamento e recebimentos ----------


def test_installments_payments_and_statement(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    plan = _approved_plan(client, ctx)
    assert plan["totals"]["approved_total"] == "320.00"

    rows = _installments(client, ctx, plan, down_payment="20", installments=3)
    assert [(r["kind"], r["installment_number"], r["amount"]) for r in rows] == [
        ("entrada", None, "20.00"),
        ("parcela", 1, "100.00"),
        ("parcela", 2, "100.00"),
        ("parcela", 3, "100.00"),
    ]
    assert rows[0]["due_date"] == str(today()) and all(r["status"] == "aberta" for r in rows)
    _installments(client, ctx, plan, down_payment="0", installments=1, expect=409)  # só uma vez

    entry, first = rows[0], rows[1]
    _pay(client, ctx, entry, "20.00")
    partial = _pay(client, ctx, first, "40.00", method="credito", fee_pct="3.5")
    assert partial["fee_amount"] == "1.40" and partial["net_amount"] == "38.60"
    _pay(client, ctx, first, "60.01", expect=409)  # acima do saldo
    _pay(client, ctx, first, "10", paid_on=str(today() + timedelta(days=1)), expect=409)

    ext = client.get(f"/financeiro/pacientes/{ctx['patient']}/extrato", headers=ctx["h"]["recep"])
    assert ext.status_code == 200, ext.text
    st = ext.json()
    assert (st["total"], st["paid"], st["balance"]) == ("320.00", "60.00", "260.00")
    by_id = {r["id"]: r for r in st["receivables"]}
    assert by_id[entry["id"]]["status"] == "paga"
    assert by_id[first["id"]]["status"] == "parcial" and by_id[first["id"]]["balance"] == "60.00"

    # Estorno (só admin/gestor): o original fica, entra um negativo; uma vez só.
    url = f"/financeiro/pagamentos/{partial['id']}/estornar"
    _post(client, ctx, url, {"reason": "Cartão recusado"}, who="recep", expect=403)
    rev = _post(client, ctx, url, {"reason": "Cartão recusado"}, who="gestor")
    assert rev["amount"] == "-40.00" and rev["reversal_of"] == partial["id"]
    _post(client, ctx, url, {"reason": "de novo"}, who="gestor", expect=409)
    _post(client, ctx, f"/financeiro/pagamentos/{rev['id']}/estornar", {"reason": "x"},
          who="gestor", expect=409)  # fmt: skip

    # Refazer o parcelamento: bloqueado com recebimento; depois do estorno da entrada, ok.
    cancel = f"/financeiro/planos/{plan['id']}/parcelamento/cancelar"
    _post(client, ctx, cancel, {"reason": "Renegociação"}, who="gestor", expect=409)
    entry_payment = next(p for p in st["payments"] if p["receivable_id"] == entry["id"])
    _post(client, ctx, f"/financeiro/pagamentos/{entry_payment['id']}/estornar",
          {"reason": "Renegociação"}, who="admin")  # fmt: skip
    assert _post(client, ctx, cancel, {"reason": "Renegociação"}, who="gestor", expect=200) == {
        "canceladas": 4
    }
    again = _installments(client, ctx, plan, down_payment="0", installments=2)
    assert [r["amount"] for r in again] == ["160.00", "160.00"]

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {
        "financeiro.parcelamento_criado", "financeiro.recebimento_registrado",
        "financeiro.recebimento_estornado", "financeiro.extrato_lido",
        "financeiro.parcelamento_cancelado",
    } <= actions  # fmt: skip


def test_receivable_rules(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    # Orçamento não aprovado não é parcelado.
    draft = _plan(client, ctx, [{"procedure_code": "PROFILAXIA"}])
    _installments(client, ctx, draft, installments=1, expect=409)

    avulsa = _post(client, ctx, "/financeiro/receber", {
        "patient_id": ctx["patient"], "description": "Clareamento caseiro",
        "due_date": str(today()), "amount": "350.00",
    })  # fmt: skip
    assert avulsa["kind"] == "avulsa" and avulsa["plan_id"] is None
    _pay(client, ctx, avulsa, "350.00", method="dinheiro")
    url = f"/financeiro/receber/{avulsa['id']}/cancelar"
    _post(client, ctx, url, {"reason": "x"}, who="gestor", expect=409)  # tem recebimento

    other = _post(client, ctx, "/financeiro/receber", {
        "patient_id": ctx["patient"], "description": "Outra", "due_date": str(today()),
        "amount": "10.00",
    })  # fmt: skip
    _post(client, ctx, f"/financeiro/receber/{other['id']}/cancelar", {"reason": "x"},
          who="recep", expect=403)  # fmt: skip
    gone = _post(client, ctx, f"/financeiro/receber/{other['id']}/cancelar", {"reason": "Erro"},
                 who="admin", expect=200)  # fmt: skip
    assert gone["status"] == "cancelada"
    _pay(client, ctx, other, "1.00", expect=409)

    listed = client.get("/financeiro/receber", params={"paciente_id": ctx["patient"]},
                        headers=ctx["h"]["recep"]).json()  # fmt: skip
    assert [r["id"] for r in listed] == [avulsa["id"]]  # canceladas ficam fora por padrão


def test_payables(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    body = {"supplier": "Dental Sul", "category": "Materiais", "due_date": str(today()),
            "amount": "1200.00"}  # fmt: skip
    _post(client, ctx, "/financeiro/pagar", body, who="recep", expect=403)
    bill = _post(client, ctx, "/financeiro/pagar", body, who="gestor")
    assert bill["status"] == "aberta"
    paid = _post(client, ctx, f"/financeiro/pagar/{bill['id']}/pagar", {"method": "boleto"},
                 who="admin", expect=200)  # fmt: skip
    assert paid["status"] == "paga" and paid["paid_on"] == str(today())
    _post(client, ctx, f"/financeiro/pagar/{bill['id']}/cancelar", {"reason": "x"},
          who="admin", expect=409)  # fmt: skip
    # No banco: conta paga não muda.
    with tenant_session(ctx["clinic"].id) as s:
        p = s.get(Payable, uuid.UUID(bill["id"]))
        p.amount = Decimal("1.00")
        with pytest.raises(IntegrityError, match="não muda"):
            s.flush()
    listed = client.get("/financeiro/pagar", params={"situacao": "paga"},
                        headers=ctx["h"]["gestor"]).json()  # fmt: skip
    assert [b["id"] for b in listed] == [bill["id"]]


def test_roles(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    pid = ctx["patient"]
    for who in ("dent", "asb"):
        for url in ("/financeiro/receber", f"/financeiro/pacientes/{pid}/extrato",
                    "/financeiro/pagar"):  # fmt: skip
            assert client.get(url, headers=ctx["h"][who]).status_code == 403, (who, url)
    assert client.get("/financeiro/pagar", headers=ctx["h"]["recep"]).status_code == 403


# ---------- garantias no banco ----------


def test_database_guards(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    plan = _approved_plan(client, ctx)
    rows = _installments(client, ctx, plan, down_payment="0", installments=1)
    rec = rows[0]
    payment = _pay(client, ctx, rec, "100.00")
    cid = ctx["clinic"].id

    for sql in ("UPDATE payments SET amount = 1", "DELETE FROM payments",
                "DELETE FROM receivables", "DELETE FROM payables"):  # fmt: skip
        with tenant_session(cid) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))

    def _insert(**fields):
        base = {
            "clinic_id": cid, "receivable_id": uuid.UUID(rec["id"]),
            "patient_id": uuid.UUID(ctx["patient"]), "amount": Decimal("1000.00"),
            "method": "pix", "fee_pct": Decimal("0"), "fee_amount": Decimal("0"),
            "net_amount": Decimal("1000.00"), "paid_on": today(), **fields,
        }  # fmt: skip
        with tenant_session(cid) as s:
            s.add(Payment(**base))
            with pytest.raises(IntegrityError):
                s.flush()

    _insert()  # acima do valor da conta
    _insert(amount=Decimal("-50.00"), net_amount=Decimal("-50.00"),
            reversal_of=uuid.UUID(payment["id"]))  # estorno que não confere  # fmt: skip

    _insert(amount=Decimal("10.00"), fee_amount=Decimal("-1.00"),
            net_amount=Decimal("11.00"))  # taxa negativa em recebimento  # fmt: skip
    _insert(amount=Decimal("10.00"), fee_amount=Decimal("20.00"),
            net_amount=Decimal("-10.00"))  # taxa maior que o valor  # fmt: skip

    with tenant_session(cid) as s:
        r = s.get(Receivable, uuid.UUID(rec["id"]))
        r.amount = Decimal("1.00")
        with pytest.raises(IntegrityError, match="recebimento"):
            s.flush()


# ---------- isolamento ----------


def test_other_clinic_cannot_see_or_use(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    plan = _approved_plan(client, a)
    rec = _installments(client, a, plan, down_payment="0", installments=1)[0]
    hb = b["h"]["admin"]

    assert (
        client.get(f"/financeiro/pacientes/{a['patient']}/extrato", headers=hb).status_code == 404
    )
    assert client.get("/financeiro/receber", headers=hb).json() == []
    _post(client, b, f"/financeiro/receber/{rec['id']}/pagamentos",
          {"amount": "1", "method": "pix"}, who="admin", expect=404)  # fmt: skip
    _post(client, b, f"/financeiro/planos/{plan['id']}/parcelamento",
          {"installments": 1}, who="admin", expect=404)  # fmt: skip

    with tenant_session(b["clinic"].id) as s:
        for model in (Receivable, Payment):
            assert s.scalar(select(func.count()).select_from(model)) == 0
        s.add(
            Receivable(
                clinic_id=b["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                kind="avulsa",
                description="x",
                due_date=today(),
                amount=Decimal("1.00"),
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        s.add(
            Receivable(
                clinic_id=a["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                kind="avulsa",
                description="x",
                due_date=today(),
                amount=Decimal("1.00"),
            )
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()


def test_dentist_reads_statement_only_when_enabled(client, make_clinic, add_member):
    from app.modules.financeiro.models import FinancialSettings

    ctx = _setup(client, make_clinic, add_member)
    pid = ctx["patient"]
    url = f"/financeiro/pacientes/{pid}/extrato"
    h = ctx["h"]
    assert client.get("/financeiro/configuracao", headers=h["dent"]).json() == {
        "dentist_can_view": False
    }
    assert client.get(url, headers=h["dent"]).status_code == 403

    # Só admin e gestor liberam.
    for who in ("dent", "recep", "asb"):
        r = client.put("/financeiro/configuracao", json={"dentist_can_view": True}, headers=h[who])
        assert r.status_code == 403, who
    r = client.put("/financeiro/configuracao", json={"dentist_can_view": True}, headers=h["gestor"])
    assert r.status_code == 200 and r.json()["dentist_can_view"] is True

    assert client.get(url, headers=h["dent"]).status_code == 200
    assert client.get(url, headers=h["asb"]).status_code == 403  # ASB continua fora
    # Liberar o extrato não libera o caixa.
    assert client.get("/financeiro/receber", headers=h["dent"]).status_code == 403
    assert client.get("/financeiro/pagar", headers=h["dent"]).status_code == 403

    r = client.put("/financeiro/configuracao", json={"dentist_can_view": False}, headers=h["admin"])
    assert r.status_code == 200
    assert client.get(url, headers=h["dent"]).status_code == 403

    with tenant_session(ctx["clinic"].id) as s:
        n = s.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "financeiro.configuracao_alterada")
        )
    assert n == 2

    # Outra clínica não vê nem herda a configuração; escrita cruzada barrada pelo RLS.
    clinic_b, user_b, pw_b = make_clinic(role=Role.ADMIN)
    hb = _auth(_login(client, user_b.email, pw_b).json()["access_token"])
    assert client.get("/financeiro/configuracao", headers=hb).json()["dentist_can_view"] is False
    with tenant_session(clinic_b.id) as s:
        assert s.scalars(select(FinancialSettings)).all() == []
        s.add(FinancialSettings(clinic_id=ctx["clinic"].id, dentist_can_view=True))
        with pytest.raises(DBAPIError):
            s.flush()
