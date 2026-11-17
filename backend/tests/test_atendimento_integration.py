"""Atendimento e evolução clínica: fluxo, autoria, agenda, imutabilidade no banco e
isolamento entre clínicas."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.prontuario.evolucao import content_hash
from app.modules.prontuario.models import (
    ClinicalNote,
    ClinicalNoteSignature,
    Encounter,
    EncounterTransfer,
    NoteKind,
)

pytestmark = pytest.mark.integration


def _setup(client, make_clinic, add_member):
    """Clínica com admin (dono-dentista), dois dentistas, ASB, gestor e recepção."""
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
    return {"clinic": clinic, "h": h, "ids": ids, "patient": patient["id"]}


def _open(client, ctx, who="dent", expect=201, **extra):
    body = {"patient_id": ctx["patient"], **extra}
    resp = client.post("/prontuario/atendimentos", json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _note(client, ctx, enc, content="Profilaxia e orientação.", who="dent", expect=201, **extra):
    resp = client.post(
        f"/prontuario/atendimentos/{enc['id']}/evolucoes",
        json={"content": content, **extra},
        headers=ctx["h"][who],
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


def _addendum(client, ctx, note, content="Correção: dente 36.", who="dent", expect=201):
    resp = client.post(
        f"/prontuario/evolucoes/{note['id']}/adendos",
        json={"content": content},
        headers=ctx["h"][who],
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


def _close(client, ctx, enc, who="dent", expect=200):
    resp = client.post(f"/prontuario/atendimentos/{enc['id']}/fechar", headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _iso(dt):
    return dt.isoformat()


# ---------- fluxo ----------


def test_encounter_note_addendum_flow(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    now = datetime.now(UTC)
    enc = _open(client, ctx)
    assert enc["status"] == "aberto" and enc["dentist_id"] == ctx["ids"]["dent"]
    assert enc["appointment_id"] is None and enc["notes"] == []

    note = _note(client, ctx, enc)
    assert note["kind"] == "evolucao" and note["author_id"] == ctx["ids"]["dent"]
    [sig] = note["signatures"]
    assert sig["method"] == "simples" and sig["content_hash"] == note["content_hash"]
    # O hash é recalculável a partir do que foi gravado.
    assert note["content_hash"] == content_hash(
        note_id=uuid.UUID(note["id"]),
        encounter_id=uuid.UUID(note["encounter_id"]),
        patient_id=uuid.UUID(note["patient_id"]),
        author_id=uuid.UUID(note["author_id"]),
        kind=note["kind"],
        amends_id=None,
        performed_at=datetime.fromisoformat(note["performed_at"]),
        content=note["content"],
    )

    # Retroativa até 7 dias; guarda também a data real do registro.
    old = _note(client, ctx, enc, "Raspagem.", performed_at=_iso(now - timedelta(days=3)))
    assert datetime.fromisoformat(old["created_at"]) - datetime.fromisoformat(
        old["performed_at"]
    ) > timedelta(days=2)
    _note(client, ctx, enc, "X", performed_at=_iso(now - timedelta(days=8)), expect=409)
    _note(client, ctx, enc, "X", performed_at=_iso(now + timedelta(hours=1)), expect=409)
    _note(client, ctx, enc, "   ", expect=422)

    closed = _close(client, ctx, enc)
    assert closed["status"] == "fechado" and closed["closed_by"] == ctx["ids"]["dent"]
    _close(client, ctx, enc, expect=409)
    _note(client, ctx, enc, "Depois de fechar", expect=409)

    # Correção depois de fechado: adendo sobre a evolução.
    add = _addendum(client, ctx, note)
    assert add["kind"] == "adendo" and add["amends_id"] == note["id"]
    _addendum(client, ctx, add, expect=409)  # adendo de adendo não

    detail = client.get(f"/prontuario/atendimentos/{enc['id']}", headers=ctx["h"]["asb"]).json()
    assert [n["id"] for n in detail["notes"]] == [note["id"], old["id"], add["id"]]

    pid = ctx["patient"]
    timeline = client.get(f"/prontuario/pacientes/{pid}/evolucoes", headers=ctx["h"]["gestor"])
    assert [n["id"] for n in timeline.json()][-1] == old["id"]  # ato clínico mais antigo
    listed = client.get(f"/prontuario/pacientes/{pid}/atendimentos", headers=ctx["h"]["dent2"])
    assert [(e["id"], e["notes"]) for e in listed.json()] == [(enc["id"], 3)]

    with tenant_session(ctx["clinic"].id) as s:
        rows = s.execute(select(AuditLog.action, AuditLog.details)).all()
    actions = {a for a, _ in rows}
    assert {
        "prontuario.atendimento_aberto",
        "prontuario.evolucao_registrada",
        "prontuario.atendimento_fechado",
        "prontuario.adendo_registrado",
        "prontuario.atendimento_lido",
        "prontuario.evolucoes_lidas",
        "prontuario.atendimentos_listados",
    } <= actions
    assert all("Profilaxia" not in str(d) for _, d in rows)  # sem texto clínico


def test_close_without_notes(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    enc = _open(client, ctx)
    assert _close(client, ctx, enc)["notes"] == []


# ---------- autoria e papéis ----------


def test_only_the_author_writes(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    enc = _open(client, ctx)
    note = _note(client, ctx, enc)

    _note(client, ctx, enc, who="dent2", expect=403)
    _note(client, ctx, enc, who="admin", expect=403)  # admin também só no próprio
    _addendum(client, ctx, note, who="dent2", expect=403)
    _close(client, ctx, enc, who="dent2", expect=403)

    # Admin (dono-dentista) atende e escreve no próprio atendimento.
    own = _open(client, ctx, who="admin")
    _note(client, ctx, own, who="admin")

    for who in ("asb", "gestor", "recep"):
        _open(client, ctx, who=who, expect=403)
        _note(client, ctx, enc, who=who, expect=403)
        _addendum(client, ctx, note, who=who, expect=403)

    pid = ctx["patient"]
    reads = (
        f"/prontuario/atendimentos/{enc['id']}",
        f"/prontuario/pacientes/{pid}/atendimentos",
        f"/prontuario/pacientes/{pid}/evolucoes",
    )
    for url in reads:
        assert client.get(url, headers=ctx["h"]["recep"]).status_code == 403, url
        for who in ("asb", "gestor", "dent2", "admin"):
            assert client.get(url, headers=ctx["h"][who]).status_code == 200, (url, who)


def test_backdated_encounter_start(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    now = datetime.now(UTC)
    _open(client, ctx, started_at=_iso(now - timedelta(days=2)))
    _open(client, ctx, started_at=_iso(now - timedelta(days=9)), expect=409)
    client.patch(f"/pacientes/{ctx['patient']}", json={"active": False}, headers=ctx["h"]["recep"])
    _open(client, ctx, expect=409)  # paciente inativo


# ---------- vindo da agenda ----------


def _book(client, ctx, start, patient=None):
    resp = client.post(
        "/agenda/agendamentos",
        json={
            "patient_id": patient or ctx["patient"],
            "dentist_id": ctx["ids"]["dent"],
            "starts_at": _iso(start),
            "ends_at": _iso(start + timedelta(minutes=30)),
        },
        headers=ctx["h"]["recep"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_from_appointment_marks_it_attended(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    now = datetime.now(UTC).replace(microsecond=0)
    past = _book(client, ctx, now - timedelta(minutes=10))
    enc = _open(client, ctx, appointment_id=past["id"])
    assert enc["appointment_id"] == past["id"]
    appt = client.get(f"/agenda/agendamentos/{past['id']}", headers=ctx["h"]["recep"]).json()
    assert appt["status"] == "atendido"
    _open(client, ctx, appointment_id=past["id"], expect=409)  # um atendimento por agendamento

    future = _book(client, ctx, now + timedelta(hours=3))
    resp = _open(client, ctx, appointment_id=future["id"], expect=409)
    assert "início" in resp["detail"]
    appt = client.get(f"/agenda/agendamentos/{future['id']}", headers=ctx["h"]["recep"]).json()
    assert appt["status"] == "agendado"  # nada mudou

    other = client.post(
        "/pacientes", json={"full_name": "José", "phone": "11911112222"}, headers=ctx["h"]["recep"]
    ).json()
    theirs = _book(client, ctx, now - timedelta(hours=2), patient=other["id"])
    _open(client, ctx, appointment_id=theirs["id"], expect=409)  # de outro paciente

    cancelled = _book(client, ctx, now - timedelta(hours=4))
    client.post(
        f"/agenda/agendamentos/{cancelled['id']}/status",
        json={"status": "cancelado"},
        headers=ctx["h"]["recep"],
    )
    _open(client, ctx, appointment_id=cancelled["id"], expect=409)
    _open(client, ctx, appointment_id=str(uuid.uuid4()), expect=404)


# ---------- garantias no banco ----------


def test_database_guards(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    enc = _open(client, ctx)
    note = _note(client, ctx, enc)
    cid = ctx["clinic"].id

    for sql in (
        "UPDATE clinical_notes SET content = 'adulterado'",
        "DELETE FROM clinical_notes",
        "UPDATE clinical_note_signatures SET content_hash = repeat('0', 64)",
        "DELETE FROM clinical_note_signatures",
        "DELETE FROM encounters",
    ):
        with tenant_session(cid) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))

    def _insert(**fields):
        base = {
            "id": uuid.uuid4(),
            "clinic_id": cid,
            "encounter_id": uuid.UUID(enc["id"]),
            "patient_id": uuid.UUID(ctx["patient"]),
            "kind": NoteKind.EVOLUCAO,
            "author_id": uuid.UUID(ctx["ids"]["dent"]),
            "content": "x",
            "performed_at": datetime.now(UTC),
            "content_hash": "a" * 64,
            **fields,
        }
        with tenant_session(cid) as s:
            s.add(ClinicalNote(**base))
            with pytest.raises(IntegrityError):
                s.flush()

    _insert(author_id=uuid.UUID(ctx["ids"]["dent2"]))  # não é o dentista do atendimento
    _insert(  # adendo de outro autor
        kind=NoteKind.ADENDO,
        amends_id=uuid.UUID(note["id"]),
        author_id=uuid.UUID(ctx["ids"]["dent2"]),
    )

    # Assinatura que não confere com a nota, ou simples de outra pessoa.
    for sig in (
        {"signer_id": uuid.UUID(ctx["ids"]["dent"]), "content_hash": "b" * 64},
        {"signer_id": uuid.UUID(ctx["ids"]["dent2"]), "content_hash": note["content_hash"]},
    ):
        with tenant_session(cid) as s:
            s.add(
                ClinicalNoteSignature(
                    clinic_id=cid, note_id=uuid.UUID(note["id"]), method="simples", **sig
                )
            )
            with pytest.raises(IntegrityError, match="assinatura"):
                s.flush()

    # Atendimento nasce aberto; só o dentista dele fecha.
    with tenant_session(cid) as s:
        s.add(
            Encounter(
                clinic_id=cid,
                patient_id=uuid.UUID(ctx["patient"]),
                dentist_id=uuid.UUID(ctx["ids"]["dent"]),
                status="fechado",
                started_at=datetime.now(UTC),
                closed_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError, match="nasce aberto"):
            s.flush()
    with tenant_session(cid) as s:
        e = s.get(Encounter, uuid.UUID(enc["id"]))
        e.status = "fechado"
        e.closed_at = datetime.now(UTC)
        e.closed_by = uuid.UUID(ctx["ids"]["dent2"])
        with pytest.raises(IntegrityError, match="só o dentista"):
            s.flush()

    _close(client, ctx, enc)
    _insert()  # atendimento fechado
    with tenant_session(cid) as s:
        e = s.get(Encounter, uuid.UUID(enc["id"]))
        e.status = "aberto"
        e.closed_at = None
        with pytest.raises(IntegrityError, match="fechado"):
            s.flush()


# ---------- isolamento ----------


def test_other_clinic_cannot_see_or_write(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    enc = _open(client, a)
    note = _note(client, a, enc)

    hb = b["h"]["dent"]
    assert client.get(f"/prontuario/atendimentos/{enc['id']}", headers=hb).status_code == 404
    resp = client.post(
        f"/prontuario/atendimentos/{enc['id']}/evolucoes", json={"content": "x"}, headers=hb
    )
    assert resp.status_code == 404
    assert (
        client.post(f"/prontuario/atendimentos/{enc['id']}/fechar", headers=hb).status_code == 404
    )
    resp = client.post(
        f"/prontuario/evolucoes/{note['id']}/adendos", json={"content": "x"}, headers=hb
    )
    assert resp.status_code == 404
    for path in ("atendimentos", "evolucoes"):
        url = f"/prontuario/pacientes/{a['patient']}/{path}"
        assert client.get(url, headers=hb).status_code == 404
    resp = client.post("/prontuario/atendimentos", json={"patient_id": a["patient"]}, headers=hb)
    assert resp.status_code == 404

    with tenant_session(b["clinic"].id) as s:
        for model in (Encounter, ClinicalNote, ClinicalNoteSignature):
            assert s.scalar(select(func.count()).select_from(model)) == 0
        # FK composta: B não pendura evolução no atendimento de A.
        s.add(
            ClinicalNote(
                clinic_id=b["clinic"].id,
                encounter_id=uuid.UUID(enc["id"]),
                patient_id=uuid.UUID(a["patient"]),
                kind=NoteKind.EVOLUCAO,
                author_id=uuid.UUID(b["ids"]["dent"]),
                content="x",
                performed_at=datetime.now(UTC),
                content_hash="a" * 64,
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        # B não abre atendimento para o paciente de A (FK composta)...
        s.add(
            Encounter(
                clinic_id=b["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                dentist_id=uuid.UUID(b["ids"]["dent"]),
                started_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        # ...nem assina a evolução de A.
        s.add(
            ClinicalNoteSignature(
                clinic_id=b["clinic"].id,
                note_id=uuid.UUID(note["id"]),
                signer_id=uuid.UUID(b["ids"]["dent"]),
                method="simples",
                content_hash=note["content_hash"],
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        # E não grava linha com o clinic_id de A (WITH CHECK do RLS).
        s.add(
            Encounter(
                clinic_id=a["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                dentist_id=uuid.UUID(b["ids"]["dent"]),
                started_at=datetime.now(UTC),
            )
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()


# ---------- transferência ----------


def test_admin_transfers_open_encounter(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    enc = _open(client, ctx)
    note = _note(client, ctx, enc)
    url = f"/prontuario/atendimentos/{enc['id']}/transferir"
    body = {"dentist_id": ctx["ids"]["dent2"], "reason": "Dentista saiu da clínica"}

    for who in ("dent", "gestor", "asb"):
        assert client.post(url, json=body, headers=ctx["h"][who]).status_code == 403
    bad = {**body, "dentist_id": ctx["ids"]["recep"]}
    assert client.post(url, json=bad, headers=ctx["h"]["admin"]).status_code == 409
    same = {**body, "dentist_id": ctx["ids"]["dent"]}
    assert client.post(url, json=same, headers=ctx["h"]["admin"]).status_code == 409

    resp = client.post(url, json=body, headers=ctx["h"]["admin"])
    assert resp.status_code == 200, resp.text
    moved = resp.json()
    assert moved["dentist_id"] == ctx["ids"]["dent2"]
    assert [(t["from_dentist_id"], t["to_dentist_id"]) for t in moved["transfers"]] == [
        (ctx["ids"]["dent"], ctx["ids"]["dent2"])
    ]

    # O novo dentista registra e fecha; o anterior não, mas o adendo à própria evolução segue.
    _note(client, ctx, enc, who="dent", expect=403)
    _note(client, ctx, enc, "Continuação do tratamento.", who="dent2")
    _addendum(client, ctx, note, who="dent")
    _close(client, ctx, enc, who="dent", expect=403)
    _close(client, ctx, enc, who="dent2")
    assert client.post(url, json=body, headers=ctx["h"]["admin"]).status_code == 409  # fechado

    # No banco: o dentista não muda sem a transferência registrada.
    other = _open(client, ctx)
    with tenant_session(ctx["clinic"].id) as s:
        e = s.get(Encounter, uuid.UUID(other["id"]))
        e.dentist_id = uuid.UUID(ctx["ids"]["dent2"])
        with pytest.raises(IntegrityError, match="transferência"):
            s.flush()

    # Transferência é append-only.
    for sql in ("UPDATE encounter_transfers SET reason = 'x'", "DELETE FROM encounter_transfers"):
        with tenant_session(ctx["clinic"].id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))


def test_other_clinic_cannot_see_or_forge_transfers(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    enc = _open(client, a)
    body = {"dentist_id": a["ids"]["dent2"], "reason": "Férias"}
    url = f"/prontuario/atendimentos/{enc['id']}/transferir"
    assert client.post(url, json=body, headers=a["h"]["admin"]).status_code == 200
    # B não transfere o atendimento de A.
    resp = client.post(url, json={**body, "dentist_id": b["ids"]["dent"]}, headers=b["h"]["admin"])
    assert resp.status_code == 404

    with tenant_session(b["clinic"].id) as s:
        assert s.scalar(select(func.count()).select_from(EncounterTransfer)) == 0
        s.add(
            EncounterTransfer(
                clinic_id=a["clinic"].id,
                encounter_id=uuid.UUID(enc["id"]),
                from_dentist_id=uuid.UUID(a["ids"]["dent2"]),
                to_dentist_id=uuid.UUID(a["ids"]["dent"]),
                reason="Forjada",
            )
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
