"""Agenda: cadeiras, agendamentos, bloqueios, conflito de horário, status e isolamento."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.agenda.models import Appointment, AppointmentStatus, EntryKind

pytestmark = pytest.mark.integration

# Amanhã às 13h UTC (10h em Brasília): sempre no futuro.
BASE = (datetime.now(UTC) + timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
PAST = BASE - timedelta(days=3)


def _iso(dt):
    return dt.isoformat()


def _setup(client, make_clinic, add_member):
    """Clínica com admin (dono-dentista), um dentista, uma recepcionista, uma cadeira e
    um paciente. Tudo marcado pela recepção."""
    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    h_admin = _auth(_login(client, admin.email, pw).json()["access_token"])
    dentist, pw_d = add_member(clinic, Role.DENTISTA)
    recep, pw_r = add_member(clinic, Role.RECEPCAO)
    h = _auth(_login(client, recep.email, pw_r).json()["access_token"])
    chair = client.post("/agenda/cadeiras", json={"name": "Cadeira 1"}, headers=h_admin).json()
    patient = client.post(
        "/pacientes", json={"full_name": "Ana Souza", "phone": "11987654321"}, headers=h
    ).json()
    return {
        "clinic": clinic,
        "h": h,
        "h_admin": h_admin,
        "admin": str(admin.id),
        "dentist": str(dentist.id),
        "recep": str(recep.id),
        "chair": chair["id"],
        "patient": patient["id"],
    }


def _book(client, ctx, start, minutes=30, *, dentist=None, chair="default", expect=201, **extra):
    body = {
        "patient_id": ctx["patient"],
        "dentist_id": dentist or ctx["dentist"],
        "starts_at": _iso(start),
        "ends_at": _iso(start + timedelta(minutes=minutes)),
        **extra,
    }
    if chair is not None:
        body["chair_id"] = ctx["chair"] if chair == "default" else chair
    resp = client.post("/agenda/agendamentos", json=body, headers=ctx["h"])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _status(client, ctx, entry, status, expect=200, **extra):
    resp = client.post(
        f"/agenda/agendamentos/{entry['id']}/status",
        json={"status": status, **extra},
        headers=ctx["h"],
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


# ---------- fluxo ----------


def test_book_list_and_detail(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    appt = _book(client, ctx, BASE, procedure="Avaliação")
    assert appt["status"] == "agendado" and appt["kind"] == "consulta"

    params = {"inicio": _iso(BASE - timedelta(hours=1)), "fim": _iso(BASE + timedelta(hours=8))}
    listed = client.get("/agenda/agendamentos", params=params, headers=ctx["h"]).json()
    assert [(e["id"], e["patient_name"]) for e in listed] == [(appt["id"], "Ana Souza")]

    other_day = {"inicio": _iso(BASE + timedelta(days=1)), "fim": _iso(BASE + timedelta(days=2))}
    assert client.get("/agenda/agendamentos", params=other_day, headers=ctx["h"]).json() == []

    by_patient = client.get(
        "/agenda/agendamentos", params={"paciente_id": ctx["patient"]}, headers=ctx["h"]
    ).json()
    assert [e["id"] for e in by_patient] == [appt["id"]]

    detail = client.get(f"/agenda/agendamentos/{appt['id']}", headers=ctx["h"]).json()
    assert [e["action"] for e in detail["historico"]] == ["criado"]


def test_list_requires_period_and_limits_it(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    assert client.get("/agenda/agendamentos", headers=ctx["h"]).status_code == 409
    long = {"inicio": _iso(BASE), "fim": _iso(BASE + timedelta(days=90))}
    assert client.get("/agenda/agendamentos", params=long, headers=ctx["h"]).status_code == 409


# ---------- conflito de horário ----------


def test_no_overlap_for_same_dentist_or_chair(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _book(client, ctx, BASE, 60)

    # Mesmo dentista, outra cadeira (sem cadeira): conflito.
    resp = client.post(
        "/agenda/agendamentos",
        json={
            "patient_id": ctx["patient"],
            "dentist_id": ctx["dentist"],
            "starts_at": _iso(BASE + timedelta(minutes=30)),
            "ends_at": _iso(BASE + timedelta(minutes=90)),
        },
        headers=ctx["h"],
    )
    assert resp.status_code == 409 and "dentista" in resp.json()["detail"]

    # Outro dentista (o admin), mesma cadeira: conflito.
    clash = _book(client, ctx, BASE + timedelta(minutes=15), dentist=ctx["admin"], expect=409)
    assert "cadeira" in clash["detail"]

    # Encostado (termina 11h, começa 11h) não conflita; outro dentista sem cadeira também não.
    _book(client, ctx, BASE + timedelta(minutes=60))
    _book(client, ctx, BASE, dentist=ctx["admin"], chair=None)


def test_cancel_and_no_show_free_the_slot(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    first = _book(client, ctx, BASE)
    _status(client, ctx, first, "cancelado", motivo="Paciente pediu")
    second = _book(client, ctx, BASE)
    assert second["id"] != first["id"]

    past = _book(client, ctx, PAST)
    _status(client, ctx, past, "falta")
    _book(client, ctx, PAST)  # horário liberado pela falta


def test_block_conflicts_with_appointments(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    lunch = {
        "dentist_id": ctx["dentist"],
        "starts_at": _iso(BASE + timedelta(hours=2)),
        "ends_at": _iso(BASE + timedelta(hours=3)),
        "notes": "Almoço",
    }
    resp = client.post("/agenda/bloqueios", json=lunch, headers=ctx["h"])
    assert resp.status_code == 201, resp.text
    block = resp.json()
    assert block["kind"] == "bloqueio" and block["patient_id"] is None

    clash = _book(client, ctx, BASE + timedelta(hours=2, minutes=30), chair=None, expect=409)
    assert "bloqueio" in clash["detail"]

    # Bloqueio sem alvo é recusado; bloqueio só pode ser cancelado.
    no_target = {k: v for k, v in lunch.items() if k != "dentist_id"}
    assert client.post("/agenda/bloqueios", json=no_target, headers=ctx["h"]).status_code == 409
    _status(client, ctx, block, "confirmado", expect=409)
    _status(client, ctx, block, "cancelado")
    _book(client, ctx, BASE + timedelta(hours=2, minutes=30), chair=None)


def test_database_exclusion_constraint_blocks_race(make_clinic, add_member, client):
    """Mesmo sem a checagem do service (duas requisições simultâneas), o banco barra."""
    ctx = _setup(client, make_clinic, add_member)
    _book(client, ctx, BASE, 60)
    with tenant_session(ctx["clinic"].id) as s:
        s.add(
            Appointment(
                clinic_id=ctx["clinic"].id,
                kind=EntryKind.CONSULTA,
                status=AppointmentStatus.AGENDADO,
                patient_id=uuid.UUID(ctx["patient"]),
                dentist_id=uuid.UUID(ctx["dentist"]),
                starts_at=BASE + timedelta(minutes=10),
                ends_at=BASE + timedelta(minutes=20),
            )
        )
        with pytest.raises(IntegrityError, match="excl_appointments_dentist_overlap"):
            s.commit()


# ---------- status e remarcação ----------


def test_status_flow(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    future = _book(client, ctx, BASE)
    assert _status(client, ctx, future, "confirmado")["status"] == "confirmado"
    resp = _status(client, ctx, future, "atendido", expect=409)
    assert "depois do horário" in resp["detail"]

    past = _book(client, ctx, PAST)
    _status(client, ctx, past, "atendido")
    _status(client, ctx, past, "cancelado", expect=409)  # atendido é final

    detail = client.get(f"/agenda/agendamentos/{future['id']}", headers=ctx["h"]).json()
    assert [(e["action"], e["status"]) for e in detail["historico"]] == [
        ("criado", "agendado"),
        ("status", "confirmado"),
    ]


def test_reschedule_resets_confirmation_and_checks_conflict(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    appt = _book(client, ctx, BASE)
    other = _book(client, ctx, BASE + timedelta(hours=2))
    _status(client, ctx, appt, "confirmado")
    url = f"/agenda/agendamentos/{appt['id']}"

    # Remarcar por cima de outro agendamento: conflito, nada muda.
    clash = {
        "starts_at": other["starts_at"],
        "ends_at": _iso(datetime.fromisoformat(other["starts_at"]) + timedelta(minutes=30)),
    }
    resp = client.patch(url, json=clash, headers=ctx["h"])
    assert resp.status_code == 409, resp.text
    assert client.get(url, headers=ctx["h"]).json()["status"] == "confirmado"

    new_start = BASE + timedelta(hours=4)
    move = {"starts_at": _iso(new_start), "ends_at": _iso(new_start + timedelta(minutes=30))}
    resp = client.patch(url, json=move, headers=ctx["h"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "agendado"  # a confirmação era do horário antigo

    # Só observação: não é remarcação nem muda status.
    _status(client, ctx, appt, "confirmado")
    resp = client.patch(url, json={"notes": "Trazer exames"}, headers=ctx["h"])
    assert resp.json()["status"] == "confirmado"

    history = client.get(url, headers=ctx["h"]).json()["historico"]
    assert [e["action"] for e in history] == [
        "criado",
        "status",
        "reagendado",
        "status",
        "alterado",
    ]
    assert history[2]["details"]["antes"]["starts_at"].startswith(BASE.date().isoformat())

    _status(client, ctx, appt, "cancelado")
    later = new_start + timedelta(hours=1)
    move = {"starts_at": _iso(later), "ends_at": _iso(later + timedelta(minutes=30))}
    assert client.patch(url, json=move, headers=ctx["h"]).status_code == 409


def test_references_are_validated(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    # Recepcionista não é dentista.
    resp = _book(client, ctx, BASE, dentist=ctx["recep"], expect=409)
    assert "Dentista" in resp["detail"]
    _book(client, ctx, BASE, dentist=str(uuid.uuid4()), expect=409)
    _book(client, ctx, BASE, chair=str(uuid.uuid4()), expect=409)

    client.patch(f"/agenda/cadeiras/{ctx['chair']}", json={"active": False}, headers=ctx["h_admin"])
    _book(client, ctx, BASE, expect=409)  # cadeira inativa

    client.patch(f"/pacientes/{ctx['patient']}", json={"active": False}, headers=ctx["h"])
    resp = _book(client, ctx, BASE, chair=None, expect=409)
    assert "inativo" in resp["detail"]


def test_chair_with_future_appointments_cannot_be_deactivated(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _book(client, ctx, BASE)
    url = f"/agenda/cadeiras/{ctx['chair']}"
    assert client.patch(url, json={"active": False}, headers=ctx["h_admin"]).status_code == 409
    dup = client.post("/agenda/cadeiras", json={"name": "Cadeira 1"}, headers=ctx["h_admin"])
    assert dup.status_code == 409


def test_audit(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    appt = _book(client, ctx, BASE)
    _status(client, ctx, appt, "confirmado")
    actions = {
        r["action"] for r in client.get("/auditoria?limit=100", headers=ctx["h_admin"]).json()
    }
    assert {
        "agenda.cadeira_criada",
        "agenda.agendamento_criado",
        "agenda.status_alterado",
    } <= actions


def test_events_are_append_only(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _book(client, ctx, BASE)
    for sql in ("UPDATE appointment_events SET status = 'falta'", "DELETE FROM appointment_events"):
        with tenant_session(ctx["clinic"].id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))


# ---------- papéis e isolamento ----------


@pytest.mark.parametrize("role", [Role.DENTISTA, Role.ASB, Role.RECEPCAO])
def test_only_managers_configure_chairs(client, make_clinic, role):
    _, user, pw = make_clinic(role=role)
    h = _auth(_login(client, user.email, pw).json()["access_token"])
    assert client.post("/agenda/cadeiras", json={"name": "X"}, headers=h).status_code == 403
    assert client.get("/agenda/cadeiras", headers=h).status_code == 200


def test_other_clinic_cannot_see_or_change(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    appt = _book(client, ctx, BASE)
    clinic_b, user_b, pw_b = make_clinic(role=Role.ADMIN)
    hb = _auth(_login(client, user_b.email, pw_b).json()["access_token"])
    url = f"/agenda/agendamentos/{appt['id']}"

    assert client.get(url, headers=hb).status_code == 404
    assert client.patch(url, json={"notes": "x"}, headers=hb).status_code == 404
    assert client.post(f"{url}/status", json={"status": "cancelado"}, headers=hb).status_code == 404
    params = {"inicio": _iso(BASE - timedelta(hours=1)), "fim": _iso(BASE + timedelta(hours=1))}
    assert client.get("/agenda/agendamentos", params=params, headers=hb).json() == []
    assert client.get("/agenda/cadeiras", headers=hb).json() == []

    # B não marca com o paciente, o dentista ou a cadeira de A.
    body = {
        "patient_id": ctx["patient"],
        "dentist_id": str(user_b.id),
        "starts_at": _iso(BASE),
        "ends_at": _iso(BASE + timedelta(minutes=30)),
    }
    assert client.post("/agenda/agendamentos", json=body, headers=hb).status_code == 409
    patient_b = client.post(
        "/pacientes", json={"full_name": "Bia", "phone": "11911112222"}, headers=hb
    ).json()
    for override in ({"dentist_id": ctx["dentist"]}, {"chair_id": ctx["chair"]}):
        resp = client.post(
            "/agenda/agendamentos",
            json={**body, "patient_id": patient_b["id"], **override},
            headers=hb,
        )
        assert resp.status_code == 409, override

    with tenant_session(clinic_b.id) as s:
        assert s.scalar(select(func.count()).select_from(Appointment)) == 0
        # FK composta: B não aponta para a cadeira de A nem direto no banco.
        s.add(
            Appointment(
                clinic_id=clinic_b.id,
                kind=EntryKind.BLOQUEIO,
                status=AppointmentStatus.AGENDADO,
                chair_id=uuid.UUID(ctx["chair"]),
                starts_at=BASE,
                ends_at=BASE + timedelta(hours=1),
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_null_times_rejected_and_one_event_per_request(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    appt = _book(client, ctx, BASE)
    url = f"/agenda/agendamentos/{appt['id']}"
    assert client.patch(url, json={"starts_at": None}, headers=ctx["h"]).status_code == 409

    later = BASE + timedelta(hours=5)
    body = {
        "starts_at": _iso(later),
        "ends_at": _iso(later + timedelta(minutes=30)),
        "notes": "Remarcado a pedido",
    }
    assert client.patch(url, json=body, headers=ctx["h"]).status_code == 200
    history = client.get(url, headers=ctx["h"]).json()["historico"]
    assert [e["action"] for e in history] == ["criado", "reagendado"]
    assert history[1]["details"]["campos"] == ["notes"]
