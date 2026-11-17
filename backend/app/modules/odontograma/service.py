"""Regras do odontograma. O commit e a auditoria ficam com o router."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.modules.odontograma import regras
from app.modules.odontograma.models import (
    EventAction,
    OdontogramEvent,
    StatusScope,
    ToothStatus,
)
from app.modules.pacientes import service as pacientes_service
from app.modules.pacientes.models import Patient
from app.modules.prontuario.models import Encounter, EncounterStatus

MAX_HISTORY = 500


class OdontogramError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(OdontogramError):
    pass


class RuleViolation(OdontogramError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    try:
        return pacientes_service.get_patient(db, patient_id)
    except pacientes_service.NotFound as exc:
        raise NotFound(exc.message) from None


# ---------- legenda ----------


def ensure_default_legend(db: Session, clinic_id: uuid.UUID) -> None:
    """Cria a legenda padrão na primeira vez que a clínica usa o odontograma.

    Idempotente e seguro com requisições simultâneas (ON CONFLICT no código). Itens da
    legenda não são apagados, só desativados, então "nenhum item" significa "nunca usou".
    """
    if db.scalar(select(ToothStatus.id).limit(1)) is not None:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "clinic_id": clinic_id,
            "code": code,
            "name": name,
            "color": color,
            "kind": kind,
            "scope": scope,
            "sort_order": i * 10,
        }
        for i, (code, name, color, kind, scope) in enumerate(regras.DEFAULT_LEGEND)
    ]
    db.execute(
        insert(ToothStatus)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["clinic_id", "code"])
    )
    db.flush()


def list_statuses(db: Session, *, include_inactive: bool = True) -> list[ToothStatus]:
    query = select(ToothStatus).order_by(ToothStatus.sort_order, ToothStatus.name)
    if not include_inactive:
        query = query.where(ToothStatus.active.is_(True))
    return list(db.scalars(query))


def get_status(db: Session, status_id: uuid.UUID) -> ToothStatus:
    status = db.get(ToothStatus, status_id)
    if status is None:
        raise NotFound("Item da legenda não encontrado.")
    return status


def create_status(db: Session, user: CurrentUser, data: dict[str, Any]) -> ToothStatus:
    ensure_default_legend(db, user.clinic_id)
    if db.scalar(select(ToothStatus.id).where(ToothStatus.code == data["code"])) is not None:
        raise RuleViolation("Já existe um item da legenda com este código.")
    status = ToothStatus(clinic_id=user.clinic_id, **data)
    db.add(status)
    db.flush()
    return status


def _used(db: Session, status: ToothStatus) -> bool:
    query = select(OdontogramEvent.id).where(OdontogramEvent.status_id == status.id).limit(1)
    return db.scalar(query) is not None


def update_status(db: Session, status: ToothStatus, changes: dict[str, Any]) -> list[str]:
    for name, value in changes.items():
        if value is None:
            raise RuleViolation(f"O campo {name} não pode ficar vazio.")
    changed = [n for n, v in changes.items() if getattr(status, n) != v]
    if {"kind", "scope"} & set(changed) and _used(db, status):
        raise RuleViolation(
            "Tipo e escopo não mudam depois de usados; crie outro item e desative este."
        )
    for name in changed:
        setattr(status, name, changes[name])
    db.flush()
    return sorted(changed)


# ---------- marcações ----------


def _events_until(db: Session, patient_id: uuid.UUID, at: datetime | None):
    query = select(OdontogramEvent).where(OdontogramEvent.patient_id == patient_id)
    if at is not None:
        query = query.where(OdontogramEvent.created_at <= at)
    return db.scalars(query.order_by(OdontogramEvent.created_at, OdontogramEvent.id))


def _as_rule_events(events) -> list[regras.Event]:
    return [regras.Event(e.tooth, e.face, e.status_id, e.action.value) for e in events]


def current_marks(db: Session, patient: Patient, at: datetime | None = None) -> set[regras.Key]:
    return regras.rebuild(_as_rule_events(_events_until(db, patient.id, at)))


def record_events(
    db: Session,
    user: CurrentUser,
    patient: Patient,
    encounter_id: uuid.UUID | None,
    events: list[dict[str, Any]],
) -> list[OdontogramEvent]:
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    # Serializa as escritas do odontograma deste paciente (o lote é validado contra o
    # estado atual).
    db.execute(select(Patient.id).where(Patient.id == patient.id).with_for_update())

    if encounter_id is not None:
        encounter = db.get(Encounter, encounter_id)
        if encounter is None:
            raise NotFound("Atendimento não encontrado.")
        if encounter.patient_id != patient.id:
            raise RuleViolation("O atendimento é de outro paciente.")
        if encounter.status is not EncounterStatus.ABERTO:
            raise RuleViolation("O atendimento está fechado.")

    ensure_default_legend(db, user.clinic_id)
    statuses = {s.id: s for s in list_statuses(db)}
    for e in events:
        status = statuses.get(e["status_id"])
        if status is None:
            raise NotFound("Item da legenda não encontrado.")
        if e["action"] == EventAction.MARCAR and not status.active:
            raise RuleViolation(f'O item "{status.name}" está desativado na legenda.')
        if status.scope is StatusScope.DENTE and e["face"] is not None:
            raise RuleViolation(f'"{status.name}" vale para o dente inteiro: não informe face.')
        if status.scope is StatusScope.FACE and e["face"] is None:
            raise RuleViolation(f'"{status.name}" é marcado por face: informe a face.')

    changes = [
        regras.Event(e["tooth"], e["face"], e["status_id"], EventAction(e["action"]).value)
        for e in events
    ]
    try:
        regras.check_batch(current_marks(db, patient), changes)
    except regras.OdontogramRuleError as exc:
        raise RuleViolation(str(exc)) from None

    rows = [
        OdontogramEvent(
            clinic_id=user.clinic_id,
            patient_id=patient.id,
            tooth=e["tooth"],
            face=e["face"],
            status_id=e["status_id"],
            action=e["action"],
            encounter_id=encounter_id,
            notes=e.get("notes"),
            recorded_by=user.user_id,
        )
        for e in events
    ]
    db.add_all(rows)
    db.flush()
    for row in rows:
        db.refresh(row)
    return rows


def history(
    db: Session, patient: Patient, *, limit: int = 100, offset: int = 0
) -> list[OdontogramEvent]:
    query = (
        select(OdontogramEvent)
        .where(OdontogramEvent.patient_id == patient.id)
        .order_by(OdontogramEvent.created_at.desc(), OdontogramEvent.id.desc())
        .limit(min(limit, MAX_HISTORY))
        .offset(offset)
    )
    return list(db.scalars(query))
