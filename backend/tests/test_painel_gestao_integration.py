"""Painel completo (Fase 5.2): metas, equipe, tendências e alertas no painel."""

from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.context import CurrentUser
from app.core.db import tenant_session
from app.core.roles import Role

pytestmark = pytest.mark.integration


def _login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def clinic(make_clinic, add_member):
    """Clínica com admin (dono-dentista) e um dentista que realizou uma restauração."""
    from app import demo
    from app.modules.pacientes import service as pacientes
    from app.modules.prontuario import atendimento_service as atendimento
    from app.modules.tratamento import service as tratamento

    c, admin, pw = make_clinic(role=Role.ADMIN)
    dentist, dpw = add_member(c, Role.DENTISTA)
    actor = CurrentUser(user_id=admin.id, clinic_id=c.id, role=Role.ADMIN)
    doc = CurrentUser(user_id=dentist.id, clinic_id=c.id, role=Role.DENTISTA)
    with tenant_session(c.id) as db:
        demo._price_table(db, actor, demo.Report())
        patient = pacientes.create_patient(db, actor, {"full_name": "P", "phone": "11999990001"})
        plan = tratamento.create_plan(
            db,
            doc,
            {
                "patient_id": patient.id,
                "items": [{"procedure_code": "DEMO-REST"}, {"procedure_code": "DEMO-PROF"}],
            },
        )
        tratamento.issue(db, doc, plan)
        items = tratamento.plan_items(db, plan)
        tratamento.decide(db, doc, plan, [i.id for i in items])
        enc = atendimento.open_encounter(db, doc, patient.id, None, None)
        tratamento.perform_item(db, doc, plan, items[0], enc.id)
        db.commit()
    return {"clinic": c, "admin": admin, "pw": pw, "dentist": dentist, "dpw": dpw}


def test_overview_has_comparison_goals_and_alerts(client, clinic):
    h = _login(client, clinic["admin"].email, clinic["pw"])
    month = date.today().replace(day=1).isoformat()
    r = client.put(
        "/painel/metas", json={"month": month, "metric": "producao", "target": "1000"}, headers=h
    )
    assert r.status_code == 201, r.text
    assert r.json()["achieved"] == "250.00"
    assert r.json()["pct"] == "25.0"
    # Mesmo mês e métrica: substitui.
    r = client.put(
        "/painel/metas", json={"month": month, "metric": "producao", "target": "500"}, headers=h
    )
    assert r.status_code == 200 and r.json()["pct"] == "50.0"

    body = client.get("/painel/visao-geral", headers=h).json()
    assert [g["metric"] for g in body["goals"]] == ["producao"]
    assert "producao" in body["comparison"]
    assert body["alerts"]["total"] == 0
    assert "conta_em_atraso" in body["alerts"]["by_rule"]


def test_goal_rules(client, clinic):
    h = _login(client, clinic["admin"].email, clinic["pw"])
    month = date.today().isoformat()
    dentist = str(clinic["dentist"].id)
    bad = client.put(
        "/painel/metas",
        json={"month": month, "metric": "recebido", "dentist_id": dentist, "target": "10"},
        headers=h,
    )
    assert bad.status_code == 422
    bad = client.put(
        "/painel/metas", json={"month": month, "metric": "xpto", "target": "10"}, headers=h
    )
    assert bad.status_code == 422
    bad = client.put(
        "/painel/metas",
        json={"month": month, "metric": "procedimentos", "target": "2.5"},
        headers=h,
    )
    assert bad.status_code == 422
    r = client.put(
        "/painel/metas",
        json={"month": month, "metric": "procedimentos", "dentist_id": dentist, "target": "4"},
        headers=h,
    )
    assert r.status_code == 201
    goal_id = r.json()["id"]
    assert r.json()["achieved"] == "1" and r.json()["pct"] == "25.0"

    goals = client.get("/painel/metas", headers=h).json()
    assert len(goals) == 1
    assert client.delete(f"/painel/metas/{goal_id}", headers=h).status_code == 204
    assert client.get("/painel/metas", headers=h).json() == []
    assert client.delete(f"/painel/metas/{goal_id}", headers=h).status_code == 404

    with tenant_session(clinic["clinic"].id) as s:
        actions = set(s.scalars(text("select action from audit_logs")).all())
    assert {"painel.meta_definida", "painel.meta_removida"} <= actions


def test_team_and_trends(client, clinic):
    h = _login(client, clinic["admin"].email, clinic["pw"])
    team = client.get("/painel/equipe", headers=h).json()
    by_id = {m["dentist_id"]: m for m in team["members"]}
    mine = by_id[str(clinic["dentist"].id)]["metrics"]
    assert mine["procedimentos"] == 1
    assert mine["producao"] == "250.00"
    assert mine["orcamentos_aprovados"] == 1 and mine["conversao_pct"] == "100.0"
    assert mine["ticket_medio"] == "430.00"
    assert mine["atendimentos"] == 1
    assert str(clinic["admin"].id) in by_id  # admin conta como dentista

    trend = client.get("/painel/tendencias", params={"meses": 3}, headers=h).json()
    assert len(trend["months"]) == 3
    last = trend["months"][-1]
    assert last["metrics"]["procedimentos"] == 1
    assert last["metrics"]["novos_pacientes"] == 1
    assert last["variation_pct"]["procedimentos"] is None  # mês anterior zerado

    hd = _login(client, clinic["dentist"].email, clinic["dpw"])
    own = client.get("/painel/minha-tendencia", params={"meses": 1}, headers=hd).json()
    assert own["dentist_id"] == str(clinic["dentist"].id)
    assert own["months"][0]["metrics"]["recebido"] is None


@pytest.mark.parametrize("role", [Role.DENTISTA, Role.ASB, Role.RECEPCAO])
def test_management_routes_restricted(client, clinic, add_member, role):
    user, pw = add_member(clinic["clinic"], role)
    h = _login(client, user.email, pw)
    assert client.get("/painel/equipe", headers=h).status_code == 403
    assert client.get("/painel/tendencias", headers=h).status_code == 403
    assert client.get("/painel/metas", headers=h).status_code == 403
    r = client.put(
        "/painel/metas",
        json={"month": date.today().isoformat(), "metric": "producao", "target": "1"},
        headers=h,
    )
    assert r.status_code == 403


def test_goals_isolated_between_clinics(client, clinic, make_clinic):
    from app.modules.painel.models import PanelGoal

    h = _login(client, clinic["admin"].email, clinic["pw"])
    r = client.put(
        "/painel/metas",
        json={"month": date.today().isoformat(), "metric": "producao", "target": "100"},
        headers=h,
    )
    goal_id = r.json()["id"]
    clinic_b, user_b, pw_b = make_clinic(role=Role.ADMIN)
    hb = _login(client, user_b.email, pw_b)
    assert client.get("/painel/metas", headers=hb).json() == []
    assert client.delete(f"/painel/metas/{goal_id}", headers=hb).status_code == 404
    # Dentista de outra clínica não recebe meta.
    r = client.put(
        "/painel/metas",
        json={
            "month": date.today().isoformat(),
            "metric": "producao",
            "dentist_id": str(clinic["dentist"].id),
            "target": "1",
        },
        headers=hb,
    )
    assert r.status_code == 422
    with tenant_session(clinic_b.id) as s:
        assert s.scalars(select(PanelGoal)).all() == []
        s.add(
            PanelGoal(
                clinic_id=clinic["clinic"].id,
                month=date.today().replace(day=1),
                metric="producao",
                target=1,
            )
        )
        with pytest.raises(DBAPIError):
            s.flush()


def test_month_and_dentist_validation(client, clinic, make_clinic):
    h = _login(client, clinic["admin"].email, clinic["pw"])
    assert client.get("/painel/tendencias", params={"ate": "9999-12"}, headers=h).status_code == 422
    r = client.put(
        "/painel/metas",
        json={"month": "1999-01-01", "metric": "producao", "target": "1"},
        headers=h,
    )
    assert r.status_code == 422
    _, other, _ = make_clinic(role=Role.ADMIN)
    r = client.get("/painel/tendencias", params={"dentista_id": str(other.id)}, headers=h)
    assert r.status_code == 422
