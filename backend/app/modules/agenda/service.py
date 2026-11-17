"""Regras da agenda. O commit e a auditoria ficam com o router.

O conflito de horário é garantido pelas constraints de exclusão do banco; a consulta prévia
(`_ensure_free`) só existe para devolver uma mensagem que diga com quem conflitou. Se duas
requisições passarem juntas pela consulta, a constraint barra a segunda (`_flush`).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.agenda import regras
from app.modules.agenda.models import (
    OCCUPYING,
    Appointment,
    AppointmentEvent,
    AppointmentStatus,
    Chair,
    EntryKind,
    EventAction,
)
from app.modules.identidade.service import active_role
from app.modules.pacientes import service as pacientes
from app.modules.pacientes.models import Patient

DENTIST_ROLES = (Role.DENTISTA, Role.ADMIN)  # admin = dono-dentista
EXCLUSION_CONSTRAINTS = {
    "excl_appointments_dentist_overlap": "O dentista já tem compromisso neste horário.",
    "excl_appointments_chair_overlap": "A cadeira já está ocupada neste horário.",
}


class AgendaError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(AgendaError):
    pass


class RuleViolation(AgendaError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def _rule(fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except regras.RuleError as exc:
        raise RuleViolation(str(exc)) from None


def _flush(db: Session) -> None:
    """Flush num savepoint, traduzindo a violação das constraints de exclusão."""
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        for name, message in EXCLUSION_CONSTRAINTS.items():
            if name in str(exc.orig):
                raise RuleViolation(message) from None
        raise


# ---------- Cadeiras ----------


def list_chairs(db: Session, *, include_inactive: bool = False) -> list[Chair]:
    query = select(Chair).order_by(Chair.name)
    if not include_inactive:
        query = query.where(Chair.active)
    return list(db.scalars(query))


def get_chair(db: Session, chair_id: uuid.UUID) -> Chair:
    chair = db.get(Chair, chair_id)
    if chair is None:
        raise NotFound("Cadeira não encontrada.")
    return chair


def _ensure_chair_name_free(db: Session, name: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(Chair.id).where(Chair.name == name)
    if exclude_id is not None:
        query = query.where(Chair.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise RuleViolation("Já existe uma cadeira com este nome.")


def create_chair(db: Session, user: CurrentUser, name: str) -> Chair:
    _ensure_chair_name_free(db, name)
    chair = Chair(clinic_id=user.clinic_id, name=name)
    db.add(chair)
    db.flush()
    return chair


def update_chair(db: Session, chair: Chair, changes: dict[str, Any]) -> Chair:
    if changes.get("name") is not None and changes["name"] != chair.name:
        _ensure_chair_name_free(db, changes["name"], exclude_id=chair.id)
        chair.name = changes["name"]
    if changes.get("active") is False and chair.active:
        upcoming = db.scalar(
            select(Appointment.id)
            .where(
                Appointment.chair_id == chair.id,
                Appointment.status.in_(OCCUPYING),
                Appointment.ends_at > now(),
            )
            .limit(1)
        )
        if upcoming is not None:
            raise RuleViolation("A cadeira tem agendamentos futuros. Remaneje-os antes.")
        chair.active = False
    elif changes.get("active") is True:
        chair.active = True
    db.flush()
    return chair


# ---------- Validações de referência ----------


def _ensure_dentist(db: Session, user: CurrentUser, dentist_id: uuid.UUID) -> None:
    if active_role(db, dentist_id, user.clinic_id) not in DENTIST_ROLES:
        raise RuleViolation("Dentista não encontrado na clínica.")


def _ensure_active_chair(db: Session, chair_id: uuid.UUID) -> None:
    chair = db.get(Chair, chair_id)
    if chair is None or not chair.active:
        raise RuleViolation("Cadeira não encontrada ou inativa.")


def _ensure_active_patient(db: Session, patient_id: uuid.UUID) -> None:
    try:
        patient = pacientes.get_patient(db, patient_id)
    except pacientes.NotFound:
        raise RuleViolation("Paciente não encontrado.") from None
    if not patient.active:
        raise RuleViolation("Paciente inativo.")


def _ensure_free(db: Session, entry: Appointment) -> None:
    # Sem autoflush: as mudanças pendentes do próprio `entry` iriam ao banco antes da
    # consulta, e a constraint de exclusão dispararia sem a mensagem amigável.
    with db.no_autoflush:
        _check_free(db, entry)


def _check_free(db: Session, entry: Appointment) -> None:
    targets = []
    if entry.dentist_id is not None:
        targets.append(("o dentista", Appointment.dentist_id == entry.dentist_id))
    if entry.chair_id is not None:
        targets.append(("a cadeira", Appointment.chair_id == entry.chair_id))
    for who, condition in targets:
        query = select(Appointment).where(
            condition,
            Appointment.status.in_(OCCUPYING),
            Appointment.starts_at < entry.ends_at,
            Appointment.ends_at > entry.starts_at,
        )
        if entry.id is not None:
            query = query.where(Appointment.id != entry.id)
        clash = db.scalar(query.order_by(Appointment.starts_at).limit(1))
        if clash is not None:
            what = "bloqueio" if clash.kind == EntryKind.BLOQUEIO else "agendamento"
            raise RuleViolation(
                f"Conflito de horário: {who} já tem um {what} de "
                f"{clash.starts_at.isoformat()} a {clash.ends_at.isoformat()}."
            )


def _event(
    db: Session,
    user: CurrentUser,
    entry: Appointment,
    action: EventAction,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AppointmentEvent(
            clinic_id=user.clinic_id,
            appointment_id=entry.id,
            action=action,
            status=entry.status,
            details=details,
            user_id=user.user_id,
        )
    )


# ---------- Agendamentos e bloqueios ----------


def get_entry(db: Session, entry_id: uuid.UUID) -> Appointment:
    entry = db.get(Appointment, entry_id)
    if entry is None:
        raise NotFound("Agendamento não encontrado.")
    return entry


def create_appointment(db: Session, user: CurrentUser, data: dict[str, Any]) -> Appointment:
    _rule(regras.check_period, data["starts_at"], data["ends_at"], is_block=False)
    _ensure_active_patient(db, data["patient_id"])
    _ensure_dentist(db, user, data["dentist_id"])
    if data.get("chair_id") is not None:
        _ensure_active_chair(db, data["chair_id"])
    return _create(db, user, EntryKind.CONSULTA, data)


def create_block(db: Session, user: CurrentUser, data: dict[str, Any]) -> Appointment:
    _rule(regras.check_period, data["starts_at"], data["ends_at"], is_block=True)
    if data.get("dentist_id") is None and data.get("chair_id") is None:
        raise RuleViolation("Informe o dentista, a cadeira ou os dois.")
    if data.get("dentist_id") is not None:
        _ensure_dentist(db, user, data["dentist_id"])
    if data.get("chair_id") is not None:
        _ensure_active_chair(db, data["chair_id"])
    return _create(db, user, EntryKind.BLOQUEIO, data)


def _create(db: Session, user: CurrentUser, kind: EntryKind, data: dict[str, Any]) -> Appointment:
    entry = Appointment(clinic_id=user.clinic_id, kind=kind, created_by=user.user_id, **data)
    entry.status = AppointmentStatus.AGENDADO
    _ensure_free(db, entry)
    db.add(entry)
    _flush(db)
    _event(db, user, entry, EventAction.CRIADO)
    db.flush()
    return entry


SCHEDULE_FIELDS = ("starts_at", "ends_at", "dentist_id", "chair_id")


def update_entry(
    db: Session, user: CurrentUser, entry: Appointment, changes: dict[str, Any]
) -> list[str]:
    """Altera horário, dentista, cadeira ou textos. Devolve os campos alterados.

    Mudar horário, dentista ou cadeira de um agendamento confirmado o volta para agendado:
    a confirmação foi do horário antigo.
    """
    for key in ("starts_at", "ends_at"):
        if key in changes and changes[key] is None:
            raise RuleViolation("Início e fim não podem ficar vazios.")
    changed = [k for k, v in changes.items() if getattr(entry, k) != v]
    if not changed:
        return []
    schedule = [k for k in changed if k in SCHEDULE_FIELDS]
    if schedule and not regras.is_editable(entry.status):
        raise RuleViolation("Só é possível remarcar agendamentos em aberto.")

    is_block = entry.kind == EntryKind.BLOQUEIO
    new = {k: changes.get(k, getattr(entry, k)) for k in SCHEDULE_FIELDS}
    _rule(regras.check_period, new["starts_at"], new["ends_at"], is_block=is_block)
    if not is_block and new["dentist_id"] is None:
        raise RuleViolation("A consulta precisa de um dentista.")
    if is_block and new["dentist_id"] is None and new["chair_id"] is None:
        raise RuleViolation("Informe o dentista, a cadeira ou os dois.")
    if "dentist_id" in schedule and new["dentist_id"] is not None:
        _ensure_dentist(db, user, new["dentist_id"])
    if "chair_id" in schedule and new["chair_id"] is not None:
        _ensure_active_chair(db, new["chair_id"])

    before = {k: _jsonable(getattr(entry, k)) for k in schedule}
    for key in changed:
        setattr(entry, key, changes[key])
    if schedule:
        _ensure_free(db, entry)
        if entry.status == AppointmentStatus.CONFIRMADO:
            entry.status = AppointmentStatus.AGENDADO
        after = {k: _jsonable(getattr(entry, k)) for k in schedule}
        _flush(db)
    # Um evento por requisição: eventos da mesma transação teriam o mesmo created_at
    # (now() do Postgres) e a ordem no histórico ficaria indefinida.
    other = sorted(set(changed) - set(schedule))
    if schedule:
        details: dict[str, Any] = {"antes": before, "depois": after}
        if other:
            details["campos"] = other
        _event(db, user, entry, EventAction.REAGENDADO, details)
    else:
        _event(db, user, entry, EventAction.ALTERADO, {"campos": other})
    db.flush()
    return sorted(changed)


def change_status(
    db: Session,
    user: CurrentUser,
    entry: Appointment,
    status: AppointmentStatus,
    reason: str | None,
) -> Appointment:
    if entry.kind == EntryKind.BLOQUEIO and status != AppointmentStatus.CANCELADO:
        raise RuleViolation("Bloqueio só pode ser cancelado.")
    _rule(regras.check_transition, entry.status, status, entry.starts_at, now())
    entry.status = status
    entry.status_reason = reason
    _event(db, user, entry, EventAction.STATUS, {"motivo": reason} if reason else None)
    db.flush()
    return entry


def list_events(db: Session, entry: Appointment) -> list[AppointmentEvent]:
    return list(
        db.scalars(
            select(AppointmentEvent)
            .where(AppointmentEvent.appointment_id == entry.id)
            .order_by(AppointmentEvent.created_at, AppointmentEvent.id)
        )
    )


@dataclass
class Row:
    entry: Appointment
    patient_name: str | None


def list_entries(
    db: Session,
    *,
    start: datetime | None,
    end: datetime | None,
    dentist_id: uuid.UUID | None = None,
    chair_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    include_cancelled: bool = True,
) -> list[Row]:
    """Compromissos que cruzam o período. Sem período, só com `patient_id` (histórico)."""
    if start is None or end is None:
        if patient_id is None:
            raise RuleViolation("Informe o período (inicio e fim) ou o paciente.")
    else:
        if end <= start:
            raise RuleViolation("O fim do período precisa ser depois do início.")
        if end - start > regras.MAX_LIST_RANGE:
            raise RuleViolation("Período máximo de consulta: 62 dias.")

    query: Select[Any] = select(Appointment, Patient.full_name, Patient.social_name).outerjoin(
        Patient, Patient.id == Appointment.patient_id
    )
    if start is not None and end is not None:
        query = query.where(Appointment.starts_at < end, Appointment.ends_at > start)
    if dentist_id is not None:
        query = query.where(Appointment.dentist_id == dentist_id)
    if chair_id is not None:
        query = query.where(Appointment.chair_id == chair_id)
    if patient_id is not None:
        query = query.where(Appointment.patient_id == patient_id)
    if not include_cancelled:
        query = query.where(Appointment.status.in_(OCCUPYING))
    rows = db.execute(query.order_by(Appointment.starts_at, Appointment.id).limit(2000)).all()
    return [Row(entry=a, patient_name=social or full) for a, full, social in rows]


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value
