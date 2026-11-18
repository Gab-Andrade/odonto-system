"""Alertas por regra: cálculo, configuração por clínica, dispensa, papéis e isolamento."""

from datetime import date, datetime, timedelta

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


def _shift(monkeypatch, days):
    """Faz o cálculo dos alertas acontecer `days` dias no futuro."""
    from app.modules.inteligencia import service

    real_now, real_today = service.now(), service.today()
    monkeypatch.setattr(service, "now", lambda: real_now + timedelta(days=days))
    monkeypatch.setattr(service, "today", lambda: real_today + timedelta(days=days))


@pytest.fixture
def scenario(make_clinic):
    """Clínica com paciente que fez profilaxia e canal (atendimento fechado) e um
    segundo orçamento aprovado e não realizado."""
    from app import demo
    from app.modules.pacientes import service as pacientes
    from app.modules.prontuario import atendimento_service as atendimento
    from app.modules.tratamento import service as tratamento

    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    actor = CurrentUser(user_id=admin.id, clinic_id=clinic.id, role=Role.ADMIN)
    with tenant_session(clinic.id) as db:
        demo._price_table(db, actor, demo.Report())
        legend = demo._legend(db, clinic.id)
        patient = pacientes.create_patient(
            db, actor, {"full_name": "Paciente Alerta", "phone": "11999990000"}
        )
        plan = tratamento.create_plan(
            db,
            actor,
            {
                "patient_id": patient.id,
                "items": [
                    {"procedure_code": "DEMO-PROF"},
                    {
                        "procedure_code": "DEMO-ENDO",
                        "tooth": 36,
                        "done_status_id": legend["endodontia"],
                    },
                ],
            },
        )
        tratamento.issue(db, actor, plan)
        items = tratamento.plan_items(db, plan)
        tratamento.decide(db, actor, plan, [i.id for i in items])
        enc = atendimento.open_encounter(db, actor, patient.id, None, None)
        for item in items:
            tratamento.perform_item(db, actor, plan, item, enc.id)
        atendimento.close_encounter(db, actor, enc)

        second = tratamento.create_plan(
            db,
            actor,
            {"patient_id": patient.id, "items": [{"procedure_code": "DEMO-REST"}]},
        )
        tratamento.issue(db, actor, second)
        tratamento.decide(db, actor, second, [i.id for i in tratamento.plan_items(db, second)])
        db.commit()
        ids = {"patient": patient.id, "plan": plan.id, "second": second.id}
    return {"clinic": clinic, "admin": admin, "pw": pw, "actor": actor, **ids}


def _codes(alerts):
    return sorted(a["code"] for a in alerts)


def test_no_alerts_right_after_treatment(client, scenario):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    r = client.get("/inteligencia/alertas", headers=h)
    assert r.status_code == 200
    assert r.json() == []


def test_alerts_appear_with_time(client, scenario, monkeypatch):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    _shift(monkeypatch, 8)
    assert _codes(client.get("/inteligencia/alertas", headers=h).json()) == [
        "orcamento_aprovado_sem_agendamento"
    ]
    _shift(monkeypatch, 40 - 8)  # acumula: 40 dias
    assert _codes(client.get("/inteligencia/alertas", headers=h).json()) == [
        "canal_sem_retorno",
        "orcamento_aprovado_sem_agendamento",
    ]


def test_profilaxia_after_six_months_and_alert_shape(client, scenario, monkeypatch):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    _shift(monkeypatch, 200)
    alerts = client.get("/inteligencia/alertas", headers=h).json()
    assert _codes(alerts) == [
        "canal_sem_retorno",
        "orcamento_aprovado_sem_agendamento",
        "profilaxia_atrasada",
    ]
    # Mais grave primeiro.
    assert alerts[0]["code"] == "canal_sem_retorno"
    assert alerts[0]["severity"] == "alta"
    prof = next(a for a in alerts if a["code"] == "profilaxia_atrasada")
    assert prof["patient_name"] == "Paciente Alerta"
    assert prof["patient_phone"] == "11999990000"
    assert prof["key"] == str(scenario["patient"])
    assert prof["dentist_id"] == str(scenario["admin"].id)

    only = client.get(
        "/inteligencia/alertas", params={"regra": "profilaxia_atrasada"}, headers=h
    ).json()
    assert _codes(only) == ["profilaxia_atrasada"]
    by_patient = client.get(
        "/inteligencia/alertas", params={"paciente_id": str(scenario["patient"])}, headers=h
    ).json()
    assert len(by_patient) == 3

    summary = client.get("/inteligencia/alertas/resumo", headers=h).json()
    assert summary["total"] == 3
    assert summary["by_rule"]["profilaxia_atrasada"] == 1


def test_future_appointment_silences_return_alerts(client, scenario, monkeypatch):
    from app.modules.agenda import service as agenda

    with tenant_session(scenario["clinic"].id) as db:
        start = datetime.now().astimezone() + timedelta(days=60)
        agenda.create_appointment(
            db,
            scenario["actor"],
            {
                "patient_id": scenario["patient"],
                "dentist_id": scenario["admin"].id,
                "starts_at": start,
                "ends_at": start + timedelta(minutes=30),
            },
        )
        db.commit()
    h = _login(client, scenario["admin"].email, scenario["pw"])
    _shift(monkeypatch, 40)
    assert client.get("/inteligencia/alertas", headers=h).json() == []


def test_rule_configuration(client, scenario, monkeypatch):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    rules = client.get("/inteligencia/regras", headers=h).json()
    assert {r["code"] for r in rules} >= {"profilaxia_atrasada", "canal_sem_retorno"}
    canal = next(r for r in rules if r["code"] == "canal_sem_retorno")
    assert canal["params"]["dias"] == 30 and canal["customized"] is False

    r = client.put(
        "/inteligencia/regras/canal_sem_retorno", json={"params": {"dias": 60}}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json()["params"]["dias"] == 60 and r.json()["customized"] is True
    r = client.put(
        "/inteligencia/regras/orcamento_aprovado_sem_agendamento",
        json={"enabled": False},
        headers=h,
    )
    assert r.status_code == 200

    _shift(monkeypatch, 40)
    assert client.get("/inteligencia/alertas", headers=h).json() == []

    bad = client.put(
        "/inteligencia/regras/canal_sem_retorno", json={"params": {"dias": 0}}, headers=h
    )
    assert bad.status_code == 422
    assert client.put("/inteligencia/regras/xpto", json={}, headers=h).status_code == 404

    with tenant_session(scenario["clinic"].id) as db:
        actions = db.scalars(
            text("select action from audit_logs where action like 'inteligencia.%'")
        ).all()
    assert "inteligencia.regra_alterada" in actions
    assert "inteligencia.alertas_listados" in actions


def test_dismiss_and_restore(client, scenario, monkeypatch):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    _shift(monkeypatch, 8)
    [alert] = client.get("/inteligencia/alertas", headers=h).json()
    body = {"code": alert["code"], "key": alert["key"], "reason": "Liguei, vai marcar"}
    r = client.post("/inteligencia/alertas/dispensar", json=body, headers=h)
    assert r.status_code == 201, r.text
    assert client.get("/inteligencia/alertas", headers=h).json() == []
    hidden = client.get(
        "/inteligencia/alertas", params={"incluir_dispensados": True}, headers=h
    ).json()
    assert hidden[0]["dismissed_until"] == r.json()["until"]
    # Dispensar de novo o que já está escondido: não encontrado.
    again = client.post("/inteligencia/alertas/dispensar", json=body, headers=h)
    assert again.status_code == 404

    r = client.post(
        "/inteligencia/alertas/reativar",
        json={"code": alert["code"], "key": alert["key"]},
        headers=h,
    )
    assert r.status_code == 201
    assert len(client.get("/inteligencia/alertas", headers=h).json()) == 1

    past = (date.today() - timedelta(days=1)).isoformat()
    r = client.post("/inteligencia/alertas/dispensar", json={**body, "until": past}, headers=h)
    assert r.status_code == 422


def test_dismissals_are_append_only(client, scenario, monkeypatch):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    _shift(monkeypatch, 8)
    [alert] = client.get("/inteligencia/alertas", headers=h).json()
    client.post(
        "/inteligencia/alertas/dispensar",
        json={"code": alert["code"], "key": alert["key"]},
        headers=h,
    )
    for sql in ("UPDATE alert_dismissals SET reason = 'x'", "DELETE FROM alert_dismissals"):
        with tenant_session(scenario["clinic"].id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))


def test_roles(client, scenario, add_member, monkeypatch):
    _shift(monkeypatch, 40)
    reception, pw = add_member(scenario["clinic"], Role.RECEPCAO)
    h = _login(client, reception.email, pw)
    assert _codes(client.get("/inteligencia/alertas", headers=h).json()) == [
        "orcamento_aprovado_sem_agendamento"
    ]  # canal sem retorno é clínico: recepção não vê
    assert (
        client.put("/inteligencia/regras/canal_sem_retorno", json={}, headers=h).status_code == 403
    )
    r = client.post(
        "/inteligencia/alertas/dispensar",
        json={"code": "canal_sem_retorno", "key": str(scenario["patient"])},
        headers=h,
    )
    assert r.status_code == 404

    dentist, pw = add_member(scenario["clinic"], Role.DENTISTA)
    hd = _login(client, dentist.email, pw)
    mine = client.get(
        "/inteligencia/alertas", params={"dentista_id": str(dentist.id)}, headers=hd
    ).json()
    assert mine == []
    assert len(client.get("/inteligencia/alertas", headers=hd).json()) == 2


def test_other_clinic_isolated(client, scenario, make_clinic, monkeypatch):
    from app.modules.inteligencia.models import AlertDismissal, AlertRuleSetting

    h = _login(client, scenario["admin"].email, scenario["pw"])
    _shift(monkeypatch, 8)
    [alert] = client.get("/inteligencia/alertas", headers=h).json()
    client.put("/inteligencia/regras/canal_sem_retorno", json={"params": {"dias": 90}}, headers=h)

    clinic_b, user_b, pw_b = make_clinic(role=Role.ADMIN)
    hb = _login(client, user_b.email, pw_b)
    assert client.get("/inteligencia/alertas", headers=hb).json() == []
    rules_b = client.get("/inteligencia/regras", headers=hb).json()
    assert next(r for r in rules_b if r["code"] == "canal_sem_retorno")["params"]["dias"] == 30
    r = client.post(
        "/inteligencia/alertas/dispensar",
        json={"code": alert["code"], "key": alert["key"]},
        headers=hb,
    )
    assert r.status_code == 404

    with tenant_session(clinic_b.id) as s:
        assert s.scalars(select(AlertRuleSetting)).all() == []
        assert s.scalars(select(AlertDismissal)).all() == []


def test_cannot_write_into_other_clinic(scenario, make_clinic):
    from app.modules.inteligencia.models import AlertDismissal, AlertRuleSetting

    clinic_b, _, _ = make_clinic(role=Role.ADMIN)
    a = scenario["clinic"].id
    rows = [
        AlertRuleSetting(clinic_id=a, code="canal_sem_retorno", params={}),
        AlertDismissal(clinic_id=a, code="canal_sem_retorno", alert_key="x", until=date.today()),
    ]
    for row in rows:
        with tenant_session(clinic_b.id) as s:
            s.add(row)
            with pytest.raises(DBAPIError):
                s.flush()


def test_unknown_rule_filter_rejected(client, scenario):
    h = _login(client, scenario["admin"].email, scenario["pw"])
    r = client.get("/inteligencia/alertas", params={"regra": "xpto"}, headers=h)
    assert r.status_code == 422
