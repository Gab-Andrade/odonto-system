"""Plano de tratamento e orçamento: preço congelado, desconto com limite, aprovação
parcial, execução no atendimento com odontograma, papéis, banco e isolamento."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.tratamento.models import TreatmentPlan, TreatmentPlanItem

pytestmark = pytest.mark.integration

ITEMS = [
    {"procedure_code": "PROFILAXIA", "description": "Profilaxia", "price": "120.00"},
    {"procedure_code": "RESTAURACAO", "description": "Restauração em resina", "price": "200.00"},
    {"procedure_code": "CANAL", "description": "Tratamento de canal", "price": "800.00"},
]


def _setup(client, make_clinic, add_member):
    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    h = {"admin": _auth(_login(client, admin.email, pw).json()["access_token"])}
    ids = {"admin": str(admin.id)}
    for key, role in (
        ("dent", Role.DENTISTA),
        ("dent2", Role.DENTISTA),
        ("asb", Role.ASB),
        ("gestor", Role.GESTOR),
        ("recep", Role.RECEPCAO),
    ):
        user, pw_u = add_member(clinic, role)
        h[key] = _auth(_login(client, user.email, pw_u).json()["access_token"])
        ids[key] = str(user.id)
    patient = client.post(
        "/pacientes", json={"full_name": "Ana Souza", "phone": "11987654321"}, headers=h["recep"]
    ).json()
    # Tabela de preço da clínica, publicada e atribuída.
    ha = h["admin"]
    table = client.post("/precificacao/tabelas", json={"name": "Base"}, headers=ha).json()
    draft = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=ha).json()[0]
    base = f"/precificacao/tabelas/{table['id']}/versoes/{draft['id']}"
    assert client.put(f"{base}/itens", json={"items": ITEMS}, headers=ha).status_code == 200
    assert client.post(f"{base}/publicar", json={}, headers=ha).status_code == 200
    body = {"table_id": table["id"], "scope_type": "clinica"}
    assert client.post("/precificacao/atribuicoes", json=body, headers=ha).status_code == 201
    legend = {s["code"]: s["id"] for s in client.get("/odontograma/legenda", headers=ha).json()}
    return {
        "clinic": clinic, "h": h, "ids": ids, "patient": patient["id"], "legend": legend,
        "table": table, "version_url": base,
    }  # fmt: skip


def _plan(client, ctx, items=None, who="dent", expect=201, **extra):
    body = {"patient_id": ctx["patient"], "items": items or [], **extra}
    resp = client.post("/tratamento/planos", json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _post(client, ctx, url, who="recep", expect=200, json=None):
    resp = client.post(url, json=json, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _issue(client, ctx, plan, who="recep", expect=200):
    return _post(client, ctx, f"/tratamento/planos/{plan['id']}/emitir", who, expect)


def _decide(client, ctx, plan, approved, who="recep", expect=200):
    return _post(client, ctx, f"/tratamento/planos/{plan['id']}/decisao", who, expect,
                 {"approved_item_ids": approved})  # fmt: skip


def _restoration(ctx, tooth=36, faces="MO"):
    return {
        "procedure_code": "RESTAURACAO",
        "tooth": tooth,
        "faces": faces,
        "planned_status_id": ctx["legend"]["restauracao_planejada"],
        "done_status_id": ctx["legend"]["restauracao"],
    }


# ---------- fluxo ----------


def test_plan_quote_approval_and_frozen_prices(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    plan = _plan(
        client,
        ctx,
        [
            _restoration(ctx),
            {"procedure_code": "PROFILAXIA"},
            {"procedure_code": "CANAL", "tooth": 46},
        ],
        title="Plano inicial",
    )
    assert plan["status"] == "rascunho" and plan["dentist_id"] == ctx["ids"]["dent"]
    assert [i["estimated_price"] for i in plan["items"]] == ["200.00", "120.00", "800.00"]
    assert all(i["unit_price"] is None for i in plan["items"])
    assert plan["items"][0]["faces"] == "MO"

    # Recepção dá desconto até o limite (5% padrão); acima, só admin/gestor.
    url = f"/tratamento/planos/{plan['id']}/desconto"
    _post(client, ctx, url, "recep", 409, {"discount_pct": "10"})
    _post(client, ctx, url, "recep", 200, {"discount_pct": "5"})
    _post(client, ctx, url, "gestor", 200, {"discount_pct": "10"})

    issued = _issue(client, ctx, plan)
    assert issued["status"] == "emitido" and issued["valid_until"] is not None
    assert [i["unit_price"] for i in issued["items"]] == ["200.00", "120.00", "800.00"]
    assert issued["totals"]["proposed"] == "1120.00"
    _post(client, ctx, url, "gestor", 409, {"discount_pct": "0"})  # emitido: fixo

    # Mudar a tabela depois não altera o orçamento emitido.
    ha = ctx["h"]["admin"]
    tid = ctx["table"]["id"]
    new = client.post(f"/precificacao/tabelas/{tid}/versoes", json={}, headers=ha).json()
    nb = f"/precificacao/tabelas/{tid}/versoes/{new['id']}"
    cheaper = [{**i, "price": "1.00"} for i in ITEMS]
    assert client.put(f"{nb}/itens", json={"items": cheaper}, headers=ha).status_code == 200
    got = client.get(f"/tratamento/planos/{plan['id']}", headers=ctx["h"]["asb"]).json()
    assert [i["unit_price"] for i in got["items"]] == ["200.00", "120.00", "800.00"]

    # Aprovação parcial: restauração e profilaxia sim, canal não.
    approved = [issued["items"][0]["id"], issued["items"][1]["id"]]
    decided = _decide(client, ctx, issued, approved)
    assert decided["status"] == "aprovado"
    assert [i["status"] for i in decided["items"]] == ["aprovado", "aprovado", "recusado"]
    assert decided["totals"]["approved_subtotal"] == "320.00"
    assert decided["totals"]["discount"] == "32.00"
    assert decided["totals"]["approved_total"] == "288.00"
    _decide(client, ctx, issued, approved, expect=409)  # já decidido

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {
        "tratamento.plano_criado", "tratamento.desconto_definido", "tratamento.orcamento_emitido",
        "tratamento.decisao_registrada", "tratamento.plano_lido",
    } <= actions  # fmt: skip


def test_perform_item_updates_odontogram_and_concludes(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    pid = ctx["patient"]
    # Achado no odontograma: restauração a fazer no 36 (M e O).
    planned = ctx["legend"]["restauracao_planejada"]
    events = [{"tooth": 36, "face": f, "status_id": planned} for f in ("M", "O")]
    client.post(f"/odontograma/pacientes/{pid}/eventos", json={"events": events},
                headers=ctx["h"]["dent"])  # fmt: skip

    plan = _issue(
        client, ctx, _plan(client, ctx, [_restoration(ctx), {"procedure_code": "PROFILAXIA"}])
    )
    rest, prof = plan["items"]
    _decide(client, ctx, plan, [rest["id"], prof["id"]])

    enc = _post(client, ctx, "/prontuario/atendimentos", "dent", 201, {"patient_id": pid})
    url = f"/tratamento/itens/{rest['id']}/realizar"
    _post(client, ctx, url, "dent2", 403, {"encounter_id": enc["id"]})  # não é o dentista dele
    _post(client, ctx, url, "recep", 403, {"encounter_id": enc["id"]})
    done = _post(client, ctx, url, "dent", 200, {"encounter_id": enc["id"]})
    item = done["items"][0]
    assert item["status"] == "realizado" and item["encounter_id"] == enc["id"]
    assert item["performed_by"] == ctx["ids"]["dent"]
    _post(client, ctx, url, "dent", 409, {"encounter_id": enc["id"]})  # já realizado

    odonto = client.get(f"/odontograma/pacientes/{pid}", headers=ctx["h"]["dent"]).json()
    tooth36 = next(t for t in odonto["teeth"] if t["tooth"] == 36)
    assert {f: [m["code"] for m in ms] for f, ms in tooth36["faces"].items()} == {
        "M": ["restauracao"],
        "O": ["restauracao"],
    }

    # Cancelar o que falta conclui o plano.
    cancel = f"/tratamento/itens/{prof['id']}/cancelar"
    _post(client, ctx, cancel, "recep", 403, {"reason": "Paciente desistiu"})
    concluded = _post(client, ctx, cancel, "dent", 200, {"reason": "Paciente desistiu"})
    assert concluded["status"] == "concluido"
    assert concluded["totals"]["approved_subtotal"] == "200.00"


def test_rules(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    # Sem itens não emite; procedimento sem preço também não.
    empty = _plan(client, ctx)
    _issue(client, ctx, empty, expect=409)
    unknown = _plan(client, ctx, [{"procedure_code": "NAO_EXISTE"}])
    assert unknown["items"][0]["estimate_error"]
    resp = _issue(client, ctx, unknown, expect=409)
    assert "NAO_EXISTE" in resp["detail"]

    # Só dentista/admin montam plano; o responsável tem de ser dentista ou admin.
    _plan(client, ctx, who="recep", expect=403)
    _plan(client, ctx, dentist_id=ctx["ids"]["recep"], who="admin", expect=409)

    # Legenda incoerente: "feito" precisa ser do tipo realizado; por face exige faces.
    bad = {**_restoration(ctx), "done_status_id": ctx["legend"]["carie"]}
    _plan(client, ctx, [bad], expect=409)
    _plan(client, ctx, [{**_restoration(ctx), "faces": None}], expect=409)
    _plan(client, ctx, [{"procedure_code": "X", "tooth": 19}], expect=422)

    # Itens só mudam no rascunho; depois, duplicar.
    plan = _plan(client, ctx, [{"procedure_code": "PROFILAXIA"}])
    item_id = plan["items"][0]["id"]
    resp = client.put(f"/tratamento/itens/{item_id}", json={"procedure_code": "CANAL"},
                      headers=ctx["h"]["dent"])  # fmt: skip
    assert resp.status_code == 200 and resp.json()["items"][0]["procedure_code"] == "CANAL"
    issued = _issue(client, ctx, plan)
    resp = client.put(f"/tratamento/itens/{item_id}", json={"procedure_code": "PROFILAXIA"},
                      headers=ctx["h"]["dent"])  # fmt: skip
    assert resp.status_code == 409
    assert (
        client.delete(f"/tratamento/itens/{item_id}", headers=ctx["h"]["dent"]).status_code == 409
    )
    copy = _post(client, ctx, f"/tratamento/planos/{plan['id']}/duplicar", "dent", 201)
    assert copy["status"] == "rascunho" and copy["items"][0]["procedure_code"] == "CANAL"

    # Decisão com item de outro plano é recusada; recusar tudo deixa o plano recusado.
    _decide(client, ctx, issued, [copy["items"][0]["id"]], expect=409)
    assert _decide(client, ctx, issued, [])["status"] == "recusado"

    # Cancelar todos os itens aprovados (sem nenhum realizado) cancela o plano.
    solo = _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "PROFILAXIA"}]))
    _decide(client, ctx, solo, [solo["items"][0]["id"]])
    gone = _post(client, ctx, f"/tratamento/itens/{solo['items'][0]['id']}/cancelar", "dent",
                 json={"reason": "Mudou de cidade"})  # fmt: skip
    assert gone["status"] == "cancelado" and gone["cancel_reason"]

    # Cancelar rascunho; aprovado não se cancela inteiro.
    cancelled = _post(
        client, ctx, f"/tratamento/planos/{copy['id']}/cancelar", json={"reason": "x"}
    )
    assert cancelled["status"] == "cancelado"

    # Configuração: só admin/gestor; vale para o limite de desconto.
    conf = {"validity_days": 15, "max_discount_pct": "12.5"}
    assert (
        client.put("/tratamento/configuracao", json=conf, headers=ctx["h"]["recep"]).status_code
        == 403
    )
    assert (
        client.put("/tratamento/configuracao", json=conf, headers=ctx["h"]["gestor"]).status_code
        == 200
    )
    again = _plan(client, ctx, [{"procedure_code": "PROFILAXIA"}])
    _post(
        client,
        ctx,
        f"/tratamento/planos/{again['id']}/desconto",
        "recep",
        200,
        {"discount_pct": "12.5"},
    )
    assert (
        client.get("/tratamento/configuracao", headers=ctx["h"]["asb"]).json()["validity_days"]
        == 15
    )

    listed = client.get(f"/tratamento/pacientes/{ctx['patient']}/planos", headers=ctx["h"]["asb"])
    assert listed.status_code == 200 and len(listed.json()) == 6


# ---------- garantias no banco ----------


def test_database_guards(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    plan = _issue(client, ctx, _plan(client, ctx, [{"procedure_code": "PROFILAXIA"}]))
    cid = ctx["clinic"].id
    with tenant_session(cid) as s:
        item = s.get(TreatmentPlanItem, uuid.UUID(plan["items"][0]["id"]))
        item.unit_price = Decimal("1.00")
        with pytest.raises(IntegrityError, match="congelado"):
            s.flush()
    with tenant_session(cid) as s:
        p = s.get(TreatmentPlan, uuid.UUID(plan["id"]))
        p.discount_pct = Decimal("50")
        with pytest.raises(IntegrityError, match="desconto"):
            s.flush()
    with tenant_session(cid) as s:
        s.execute(select(1))
        with pytest.raises(IntegrityError, match="não é apagado"):
            s.execute(text("DELETE FROM treatment_plan_items"))
    with tenant_session(cid) as s:
        s.execute(select(1))
        with pytest.raises(DBAPIError, match="permission denied"):
            s.execute(text("DELETE FROM treatment_plans"))
    # Item não entra em orçamento emitido.
    with tenant_session(cid) as s:
        s.add(
            TreatmentPlanItem(
                clinic_id=cid,
                plan_id=uuid.UUID(plan["id"]),
                patient_id=uuid.UUID(ctx["patient"]),
                procedure_code="CANAL",
            )
        )
        with pytest.raises(IntegrityError, match="rascunho"):
            s.flush()
    # Recusado é final.
    client.post(f"/tratamento/planos/{plan['id']}/decisao", json={"approved_item_ids": []},
                headers=ctx["h"]["recep"])  # fmt: skip
    with tenant_session(cid) as s:
        item = s.get(TreatmentPlanItem, uuid.UUID(plan["items"][0]["id"]))
        item.status = "aprovado"
        with pytest.raises(IntegrityError, match="não muda"):
            s.flush()


# ---------- papéis e isolamento ----------


def test_other_clinic_cannot_see_or_use(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    plan = _issue(client, a, _plan(client, a, [{"procedure_code": "PROFILAXIA"}]))
    hb = b["h"]["admin"]

    assert client.get(f"/tratamento/planos/{plan['id']}", headers=hb).status_code == 404
    assert client.get(f"/tratamento/pacientes/{a['patient']}/planos", headers=hb).status_code == 404
    assert client.post(f"/tratamento/planos/{plan['id']}/decisao", json={"approved_item_ids": []},
                       headers=hb).status_code == 404  # fmt: skip
    item = plan["items"][0]["id"]
    assert client.post(f"/tratamento/itens/{item}/cancelar", json={"reason": "x"},
                       headers=hb).status_code == 404  # fmt: skip
    _plan(client, b, patient_id=a["patient"], who="admin", expect=404)

    with tenant_session(b["clinic"].id) as s:
        assert s.scalar(select(func.count()).select_from(TreatmentPlan)) == 0
        # FK composta: B não pendura item no plano de A.
        s.add(
            TreatmentPlanItem(
                clinic_id=b["clinic"].id,
                plan_id=uuid.UUID(plan["id"]),
                patient_id=uuid.UUID(a["patient"]),
                procedure_code="X",
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        s.add(
            TreatmentPlan(
                clinic_id=a["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                dentist_id=uuid.UUID(a["ids"]["dent"]),
            )
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
