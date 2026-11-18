"""Regras do odontograma. O commit e a auditoria ficam com o router."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.modules.odontograma import arcada, regras
from app.modules.odontograma.models import (
    ArchConfig,
    Dentition,
    Display3D,
    EventAction,
    OdontogramEvent,
    PersonalColor,
    StatusKind,
    StatusScope,
    ToothNote,
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
            "display_3d": "ocultar" if code in regras.HIDDEN_IN_3D else "colorir",
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


@dataclass(frozen=True)
class StatusView:
    """Item da legenda como uma pessoa o vê: `color` é a pessoal, se houver; senão, a da
    clínica. Cópia sem vínculo com a sessão, para não gravar a cor pessoal no item."""

    id: uuid.UUID
    code: str
    name: str
    color: str
    clinic_color: str
    personal: bool
    kind: StatusKind
    scope: StatusScope
    sort_order: int
    display_3d: Display3D
    active: bool


def statuses_for(
    db: Session, user_id: uuid.UUID, *, include_inactive: bool = True
) -> list[StatusView]:
    personal = dict(
        db.execute(
            select(PersonalColor.status_id, PersonalColor.color).where(
                PersonalColor.user_id == user_id
            )
        ).all()
    )
    return [
        StatusView(
            id=s.id,
            code=s.code,
            name=s.name,
            color=personal.get(s.id, s.color),
            clinic_color=s.color,
            personal=s.id in personal,
            kind=s.kind,
            scope=s.scope,
            sort_order=s.sort_order,
            display_3d=s.display_3d,
            active=s.active,
        )
        for s in list_statuses(db, include_inactive=include_inactive)
    ]


def set_personal_color(
    db: Session, user: CurrentUser, status: ToothStatus, color: str | None
) -> bool:
    """Grava (ou, com `None`, apaga) a cor pessoal. Devolve se algo mudou."""
    row = db.scalar(
        select(PersonalColor).where(
            PersonalColor.user_id == user.user_id, PersonalColor.status_id == status.id
        )
    )
    if color is None:
        if row is None:
            return False
        db.delete(row)
    elif row is None:
        db.add(
            PersonalColor(
                clinic_id=user.clinic_id, user_id=user.user_id, status_id=status.id, color=color
            )
        )
    elif row.color == color:
        return False
    else:
        row.color = color
    db.flush()
    return True


def add_tooth_note(
    db: Session, user: CurrentUser, patient: Patient, tooth: int, text: str
) -> ToothNote:
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    note = ToothNote(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        tooth=tooth,
        text=text,
        created_by=user.user_id,
    )
    db.add(note)
    db.flush()
    db.refresh(note)  # created_at vem do banco
    return note


def tooth_notes(db: Session, patient: Patient, at: datetime | None = None) -> list[ToothNote]:
    query = select(ToothNote).where(ToothNote.patient_id == patient.id)
    if at is not None:
        query = query.where(ToothNote.created_at <= at)
    return list(db.scalars(query.order_by(ToothNote.created_at.desc())))


def get_status(db: Session, status_id: uuid.UUID) -> ToothStatus:
    status = db.get(ToothStatus, status_id)
    if status is None:
        raise NotFound("Item da legenda não encontrado.")
    return status


def create_status(db: Session, user: CurrentUser, data: dict[str, Any]) -> ToothStatus:
    ensure_default_legend(db, user.clinic_id)
    if db.scalar(select(ToothStatus.id).where(ToothStatus.code == data["code"])) is not None:
        raise RuleViolation("Já existe um item da legenda com este código.")
    _check_display(data["scope"], data.get("display_3d", Display3D.COLORIR))
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
    _check_display(changes.get("scope", status.scope), changes.get("display_3d", status.display_3d))
    for name in changed:
        setattr(status, name, changes[name])
    db.flush()
    return sorted(changed)


def _check_display(scope: StatusScope, display: Display3D) -> None:
    if Display3D(display) is Display3D.OCULTAR and StatusScope(scope) is not StatusScope.DENTE:
        raise RuleViolation("Só item de dente inteiro pode ocultar o dente no 3D.")


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


# ---------- arcada ----------


@dataclass(frozen=True)
class Arch:
    """Arcada vigente: a registrada mais recente ou, sem registro, a sugerida pela idade."""

    dentition: str
    teeth: list[int]
    config: ArchConfig | None

    @property
    def source(self) -> str:
        return "registrada" if self.config else "padrao"


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def effective_arch(db: Session, patient: Patient, at: datetime | None = None) -> Arch:
    query = select(ArchConfig).where(ArchConfig.patient_id == patient.id)
    if at is not None:
        query = query.where(ArchConfig.created_at <= at)
    config = db.scalars(
        query.order_by(ArchConfig.created_at.desc(), ArchConfig.id.desc()).limit(1)
    ).first()
    if config is not None:
        return Arch(config.dentition.value, arcada.sort_teeth(config.teeth), config)
    ref = today() if at is None else at.astimezone(ZoneInfo(get_settings().clinic_timezone)).date()
    dentition, teeth = arcada.default_for(patient.birth_date, ref)
    return Arch(dentition, teeth, None)


def record_arch(
    db: Session, user: CurrentUser, patient: Patient, data: dict[str, Any]
) -> ArchConfig:
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    dentition = Dentition(data["dentition"]).value
    try:
        if data.get("teeth") is not None:
            if data.get("third_molars") is not None:
                raise arcada.ArchRuleError(
                    "Informe os terceiros molares dentro da lista de dentes, não à parte."
                )
            teeth = arcada.validate(dentition, data["teeth"])
        else:
            molars = data.get("third_molars")
            if molars is None and dentition == arcada.PERMANENTE:
                molars = arcada.THIRD_MOLARS
            teeth = arcada.preset(dentition, molars)
    except arcada.ArchRuleError as exc:
        raise RuleViolation(str(exc)) from None
    config = ArchConfig(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        dentition=dentition,
        teeth=teeth,
        notes=data.get("notes"),
        recorded_by=user.user_id,
    )
    db.add(config)
    db.flush()
    db.refresh(config)
    return config
