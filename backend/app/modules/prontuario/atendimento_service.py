"""Regras de atendimento e evolução clínica. O commit e a auditoria ficam com o router.

Autoria: só o dentista do atendimento registra evoluções nele e o fecha; só o autor de uma
evolução faz adendo a ela. O papel (dentista ou admin) é conferido no router.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.modules.agenda import service as agenda_service
from app.modules.agenda.models import AppointmentStatus, EntryKind
from app.modules.pacientes.models import Patient
from app.modules.prontuario import evolucao
from app.modules.prontuario.models import (
    ClinicalNote,
    ClinicalNoteSignature,
    Encounter,
    EncounterStatus,
    NoteKind,
    SignatureMethod,
)
from app.modules.prontuario.service import Forbidden, NotFound, RuleViolation, get_patient


def now() -> datetime:
    return datetime.now(UTC)


def _check_performed_at(value: datetime, current: datetime) -> None:
    try:
        evolucao.check_performed_at(value, current)
    except evolucao.EvolutionRuleError as exc:
        raise RuleViolation(str(exc)) from None


# ---------- atendimento ----------


def get_encounter(db: Session, encounter_id: uuid.UUID) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:  # de outra clínica também cai aqui (RLS)
        raise NotFound("Atendimento não encontrado.")
    return encounter


def _ensure_own_open(user: CurrentUser, encounter: Encounter) -> None:
    if encounter.dentist_id != user.user_id:
        raise Forbidden("Só o dentista deste atendimento pode registrar nele.")
    if encounter.status is not EncounterStatus.ABERTO:
        raise RuleViolation("Atendimento fechado: correções entram como adendo.")


def open_encounter(
    db: Session,
    user: CurrentUser,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID | None,
    started_at: datetime | None,
) -> Encounter:
    """Abre um atendimento com quem está logado como dentista.

    Vindo da agenda, o agendamento passa para atendido (a agenda exige que o horário de
    início já tenha chegado).
    """
    patient = get_patient(db, patient_id)
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    current = now()
    started = started_at or current
    _check_performed_at(started, current)
    encounter = Encounter(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        dentist_id=user.user_id,
        status=EncounterStatus.ABERTO,
        started_at=started,
    )
    if appointment_id is not None:
        try:
            appointment = agenda_service.get_entry(db, appointment_id)
        except agenda_service.NotFound:
            raise NotFound("Agendamento não encontrado.") from None
        if appointment.kind is not EntryKind.CONSULTA or appointment.patient_id != patient.id:
            raise RuleViolation("O agendamento não é deste paciente.")
        taken = select(Encounter.id).where(Encounter.appointment_id == appointment.id)
        if db.scalar(taken.limit(1)) is not None:
            raise RuleViolation("Este agendamento já tem um atendimento.")
        if appointment.status is not AppointmentStatus.ATENDIDO:
            try:
                agenda_service.change_status(
                    db, user, appointment, AppointmentStatus.ATENDIDO, None
                )
            except agenda_service.AgendaError as exc:
                raise RuleViolation(exc.message) from None
        encounter.appointment_id = appointment.id
    db.add(encounter)
    db.flush()
    db.refresh(encounter)
    return encounter


def close_encounter(db: Session, user: CurrentUser, encounter: Encounter) -> None:
    """Fecha o atendimento (pode não ter evolução: paciente veio e nada foi feito)."""
    _ensure_own_open(user, encounter)
    encounter.status = EncounterStatus.FECHADO
    encounter.closed_at = now()
    encounter.closed_by = user.user_id
    db.flush()


# ---------- evolução e adendo ----------


def _new_note(
    db: Session,
    user: CurrentUser,
    encounter: Encounter,
    kind: NoteKind,
    content: str,
    performed_at: datetime,
    amends_id: uuid.UUID | None = None,
) -> ClinicalNote:
    note_id = uuid.uuid4()
    digest = evolucao.content_hash(
        note_id=note_id,
        encounter_id=encounter.id,
        patient_id=encounter.patient_id,
        author_id=user.user_id,
        kind=kind,
        amends_id=amends_id,
        performed_at=performed_at,
        content=content,
    )
    note = ClinicalNote(
        id=note_id,
        clinic_id=user.clinic_id,
        encounter_id=encounter.id,
        patient_id=encounter.patient_id,
        kind=kind,
        amends_id=amends_id,
        author_id=user.user_id,
        content=content,
        performed_at=performed_at,
        content_hash=digest,
    )
    db.add(note)
    db.flush()
    # Assinatura eletrônica simples: o autor autenticado assina o hash do conteúdo.
    db.add(
        ClinicalNoteSignature(
            clinic_id=user.clinic_id,
            note_id=note.id,
            signer_id=user.user_id,
            method=SignatureMethod.SIMPLES,
            content_hash=digest,
        )
    )
    db.flush()
    db.refresh(note)
    return note


def add_note(
    db: Session,
    user: CurrentUser,
    encounter: Encounter,
    content: str,
    performed_at: datetime | None,
) -> ClinicalNote:
    _ensure_own_open(user, encounter)
    current = now()
    performed = performed_at or current
    _check_performed_at(performed, current)
    return _new_note(db, user, encounter, NoteKind.EVOLUCAO, content, performed)


def get_note(db: Session, note_id: uuid.UUID) -> ClinicalNote:
    note = db.get(ClinicalNote, note_id)
    if note is None:
        raise NotFound("Evolução não encontrada.")
    return note


def add_addendum(db: Session, user: CurrentUser, note: ClinicalNote, content: str) -> ClinicalNote:
    """Adendo sobre uma evolução, a qualquer tempo (inclusive com atendimento fechado)."""
    if note.kind is not NoteKind.EVOLUCAO:
        raise RuleViolation("O adendo é feito sobre a evolução, não sobre outro adendo.")
    if note.author_id != user.user_id:
        raise Forbidden("Só o autor da evolução pode fazer adendo a ela.")
    encounter = get_encounter(db, note.encounter_id)
    return _new_note(db, user, encounter, NoteKind.ADENDO, content, now(), amends_id=note.id)


# ---------- leitura ----------


@dataclass
class EncounterRow:
    encounter: Encounter
    notes: int


MAX_PAGE = 500


def list_encounters(
    db: Session, patient: Patient, *, limit: int = 100, offset: int = 0
) -> list[EncounterRow]:
    query = (
        select(Encounter, func.count(ClinicalNote.id))
        .outerjoin(ClinicalNote, ClinicalNote.encounter_id == Encounter.id)
        .where(Encounter.patient_id == patient.id)
        .group_by(Encounter.id)
        .order_by(Encounter.started_at.desc(), Encounter.id)
        .limit(min(limit, MAX_PAGE))
        .offset(offset)
    )
    return [EncounterRow(encounter=e, notes=n) for e, n in db.execute(query).all()]


def signatures_by_note(
    db: Session, notes: list[ClinicalNote]
) -> dict[uuid.UUID, list[ClinicalNoteSignature]]:
    result: dict[uuid.UUID, list[ClinicalNoteSignature]] = {n.id: [] for n in notes}
    if notes:
        query = (
            select(ClinicalNoteSignature)
            .where(ClinicalNoteSignature.note_id.in_(list(result)))
            .order_by(ClinicalNoteSignature.signed_at)
        )
        for sig in db.scalars(query):
            result[sig.note_id].append(sig)
    return result


def encounter_notes(db: Session, encounter: Encounter) -> list[ClinicalNote]:
    query = (
        select(ClinicalNote)
        .where(ClinicalNote.encounter_id == encounter.id)
        .order_by(ClinicalNote.created_at, ClinicalNote.id)
    )
    return list(db.scalars(query))


def patient_notes(
    db: Session, patient: Patient, *, limit: int = 100, offset: int = 0
) -> list[ClinicalNote]:
    """Linha do tempo do paciente: mais recente primeiro pela data do ato clínico."""
    query = (
        select(ClinicalNote)
        .where(ClinicalNote.patient_id == patient.id)
        .order_by(ClinicalNote.performed_at.desc(), ClinicalNote.created_at.desc(), ClinicalNote.id)
        .limit(min(limit, MAX_PAGE))
        .offset(offset)
    )
    return list(db.scalars(query))
