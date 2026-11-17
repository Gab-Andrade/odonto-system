"""Regras do plano de tratamento e orçamento. O commit e a auditoria ficam com o router."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.service import active_role
from app.modules.odontograma import regras as odonto
from app.modules.odontograma import service as odonto_service
from app.modules.odontograma.models import EventAction, StatusScope, ToothStatus
from app.modules.pacientes import service as pacientes_service
from app.modules.pacientes.models import Patient
from app.modules.precificacao import service as pricing
from app.modules.prontuario.models import Encounter, EncounterStatus
from app.modules.tratamento import regras
from app.modules.tratamento.models import (
    DEFAULT_MAX_DISCOUNT_PCT,
    DEFAULT_VALIDITY_DAYS,
    ItemStatus,
    PlanStatus,
    TreatmentPlan,
    TreatmentPlanItem,
    TreatmentSettings,
)

DENTIST_ROLES = (Role.DENTISTA, Role.ADMIN)
UNLIMITED_DISCOUNT = (Role.ADMIN, Role.GESTOR)
ITEM_FIELDS = (
    "procedure_code",
    "tooth",
    "faces",
    "notes",
    "planned_status_id",
    "done_status_id",
    "sort_order",
)


class TreatmentError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(TreatmentError):
    pass


class RuleViolation(TreatmentError):
    pass


class Forbidden(TreatmentError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def _rule(fn, *args) -> Any:
    try:
        return fn(*args)
    except (regras.PlanRuleError, odonto.OdontogramRuleError) as exc:
        raise RuleViolation(str(exc)) from None


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    try:
        return pacientes_service.get_patient(db, patient_id)
    except pacientes_service.NotFound as exc:
        raise NotFound(exc.message) from None


# ---------- configuração ----------


@dataclass
class Settings:
    validity_days: int
    max_discount_pct: Decimal


def get_clinic_settings(db: Session) -> Settings:
    row = db.scalar(select(TreatmentSettings))
    if row is None:
        return Settings(DEFAULT_VALIDITY_DAYS, DEFAULT_MAX_DISCOUNT_PCT)
    return Settings(row.validity_days, row.max_discount_pct)


def save_settings(db: Session, user: CurrentUser, validity_days: int, max_pct: Decimal) -> None:
    stmt = insert(TreatmentSettings).values(
        id=uuid.uuid4(),
        clinic_id=user.clinic_id,
        validity_days=validity_days,
        max_discount_pct=max_pct,
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["clinic_id"],
            set_={"validity_days": validity_days, "max_discount_pct": max_pct, "updated_at": now()},
        )
    )
    db.flush()


# ---------- plano ----------


def get_plan(db: Session, plan_id: uuid.UUID, *, lock: bool = False) -> TreatmentPlan:
    query = select(TreatmentPlan).where(TreatmentPlan.id == plan_id)
    if lock:
        query = query.with_for_update()
    plan = db.scalar(query)
    if plan is None:  # de outra clínica também cai aqui (RLS)
        raise NotFound("Plano de tratamento não encontrado.")
    return plan


def plan_items(db: Session, plan: TreatmentPlan) -> list[TreatmentPlanItem]:
    query = (
        select(TreatmentPlanItem)
        .where(TreatmentPlanItem.plan_id == plan.id)
        .order_by(TreatmentPlanItem.sort_order, TreatmentPlanItem.created_at, TreatmentPlanItem.id)
    )
    return list(db.scalars(query))


def list_plans(db: Session, patient: Patient) -> list[TreatmentPlan]:
    query = (
        select(TreatmentPlan)
        .where(TreatmentPlan.patient_id == patient.id)
        .order_by(TreatmentPlan.created_at.desc())
    )
    return list(db.scalars(query))


def _ensure_dentist(db: Session, user: CurrentUser, dentist_id: uuid.UUID) -> None:
    if active_role(db, dentist_id, user.clinic_id) not in DENTIST_ROLES:
        raise RuleViolation("Dentista responsável não encontrado na clínica.")


def _ensure_draft(plan: TreatmentPlan) -> None:
    if plan.status is not PlanStatus.RASCUNHO:
        raise RuleViolation("Só o rascunho é alterado; duplique o plano para mudar.")


def _check_statuses(db: Session, data: dict[str, Any]) -> None:
    """Itens da legenda informados existem; o 'feito' tem de ser do tipo realizado e o
    escopo tem de combinar com as faces do item."""
    for field in ("planned_status_id", "done_status_id"):
        status_id = data.get(field)
        if status_id is None:
            continue
        status = db.get(ToothStatus, status_id)
        if status is None:
            raise NotFound("Item da legenda do odontograma não encontrado.")
        if data.get("tooth") is None:
            raise RuleViolation("Para ligar ao odontograma, informe o dente.")
        if status.scope is StatusScope.FACE and not data.get("faces"):
            raise RuleViolation(f'"{status.name}" é marcado por face: informe as faces.')
        if field == "done_status_id" and status.kind.value != "realizado":
            raise RuleViolation(f'"{status.name}" não é do tipo realizado.')


def _next_sort_order(db: Session, plan: TreatmentPlan) -> int:
    last = db.scalar(
        select(func.max(TreatmentPlanItem.sort_order)).where(TreatmentPlanItem.plan_id == plan.id)
    )
    return 0 if last is None else last + 10


def _new_item(db: Session, user: CurrentUser, plan: TreatmentPlan, data: dict[str, Any]):
    _check_statuses(db, data)
    order = data.get("sort_order")
    item = TreatmentPlanItem(
        clinic_id=user.clinic_id,
        plan_id=plan.id,
        patient_id=plan.patient_id,
        **{f: data.get(f) for f in ITEM_FIELDS if f != "sort_order"},
        sort_order=_next_sort_order(db, plan) if order is None else order,
    )
    db.add(item)
    return item


def create_plan(db: Session, user: CurrentUser, data: dict[str, Any]) -> TreatmentPlan:
    patient = get_patient(db, data["patient_id"])
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    dentist_id = data.get("dentist_id")
    if dentist_id is None:
        if user.role not in DENTIST_ROLES:
            raise RuleViolation("Informe o dentista responsável.")
        dentist_id = user.user_id
    _ensure_dentist(db, user, dentist_id)
    plan = TreatmentPlan(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        dentist_id=dentist_id,
        status=PlanStatus.RASCUNHO,
        title=data.get("title"),
        notes=data.get("notes"),
        created_by=user.user_id,
    )
    db.add(plan)
    db.flush()
    for item in data.get("items", []):
        _new_item(db, user, plan, item)
        db.flush()  # a ordem padrão do próximo item depende deste
    return plan


def update_plan(db: Session, user: CurrentUser, plan: TreatmentPlan, changes: dict) -> list[str]:
    _ensure_draft(plan)
    if "dentist_id" in changes:
        if changes["dentist_id"] is None:
            raise RuleViolation("O plano precisa de um dentista responsável.")
        _ensure_dentist(db, user, changes["dentist_id"])
    changed = [n for n, v in changes.items() if getattr(plan, n) != v]
    for name in changed:
        setattr(plan, name, changes[name])
    db.flush()
    return sorted(changed)


def set_discount(db: Session, user: CurrentUser, plan: TreatmentPlan, pct: Decimal) -> None:
    _ensure_draft(plan)
    limit = None if user.role in UNLIMITED_DISCOUNT else get_clinic_settings(db).max_discount_pct
    _rule(regras.check_discount, pct, limit)
    plan.discount_pct = pct
    db.flush()


def add_item(db: Session, user: CurrentUser, plan: TreatmentPlan, data: dict) -> TreatmentPlanItem:
    _ensure_draft(plan)
    item = _new_item(db, user, plan, data)
    db.flush()
    return item


def get_item(db: Session, item_id: uuid.UUID) -> TreatmentPlanItem:
    item = db.get(TreatmentPlanItem, item_id)
    if item is None:
        raise NotFound("Item do plano não encontrado.")
    return item


def update_item(db: Session, plan: TreatmentPlan, item: TreatmentPlanItem, data: dict) -> None:
    _ensure_draft(plan)
    _check_statuses(db, data)
    for field in ITEM_FIELDS:
        if field == "sort_order" and data.get(field) is None:
            continue  # mantém a posição
        setattr(item, field, data.get(field))
    db.flush()


def delete_item(db: Session, plan: TreatmentPlan, item: TreatmentPlanItem) -> None:
    _ensure_draft(plan)
    db.delete(item)
    db.flush()


def estimate(db: Session, plan: TreatmentPlan, item: TreatmentPlanItem):
    """Preço que seria congelado hoje (só leitura). Devolve (resolução, erro)."""
    try:
        return pricing.resolve(
            db, procedure_code=item.procedure_code, dentist_id=plan.dentist_id
        ), None
    except pricing.PriceNotFound as exc:
        return None, exc.message


def issue(db: Session, user: CurrentUser, plan: TreatmentPlan) -> None:
    """Emite o orçamento: congela o preço de cada item e fixa a validade."""
    _ensure_draft(plan)
    items = plan_items(db, plan)
    if not items:
        raise RuleViolation("Inclua ao menos um procedimento antes de emitir.")
    patient = get_patient(db, plan.patient_id)
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    _ensure_dentist(db, user, plan.dentist_id)
    missing = []
    for item in items:
        resolution, error = estimate(db, plan, item)
        if resolution is None:
            missing.append(f"{item.procedure_code} ({error})")
            continue
        snapshot = pricing.freeze(db, user, resolution, dentist_id=plan.dentist_id, insurer_id=None)
        item.price_snapshot_id = snapshot.id
        item.unit_price = snapshot.price
        item.description = snapshot.description
    if missing:
        raise RuleViolation("Sem preço para: " + "; ".join(missing))
    settings = get_clinic_settings(db)
    plan.status = PlanStatus.EMITIDO
    plan.issued_at = now()
    plan.issued_by = user.user_id
    plan.valid_until = date.fromordinal(today().toordinal() + settings.validity_days)
    db.flush()


def decide(
    db: Session, user: CurrentUser, plan: TreatmentPlan, approved_ids: list[uuid.UUID]
) -> None:
    """Registra a decisão do paciente: itens listados aprovados, os demais recusados."""
    if plan.status is not PlanStatus.EMITIDO:
        raise RuleViolation("Só orçamento emitido recebe a decisão do paciente.")
    if regras.is_expired(plan.status, plan.valid_until, today()):
        raise RuleViolation("Orçamento vencido: duplique e emita de novo para atualizar os preços.")
    items = plan_items(db, plan)
    ids = set(approved_ids)
    unknown = ids - {i.id for i in items}
    if unknown:
        raise RuleViolation("Item aprovado que não é deste orçamento.")
    for item in items:
        item.status = ItemStatus.APROVADO if item.id in ids else ItemStatus.RECUSADO
    plan.status = regras.plan_after_decision(len(ids))
    plan.decided_at = now()
    plan.decided_by = user.user_id
    db.flush()


def cancel_plan(db: Session, plan: TreatmentPlan, reason: str) -> None:
    if plan.status not in (PlanStatus.RASCUNHO, PlanStatus.EMITIDO):
        raise RuleViolation(
            "Só rascunho ou orçamento emitido é cancelado; em aprovado, cancele os itens."
        )
    plan.status = PlanStatus.CANCELADO
    plan.cancelled_at = now()
    plan.cancel_reason = reason
    db.flush()


def duplicate(db: Session, user: CurrentUser, plan: TreatmentPlan) -> TreatmentPlan:
    """Novo rascunho com os mesmos procedimentos (para orçamento vencido, recusado...)."""
    copy = create_plan(
        db,
        user,
        {
            "patient_id": plan.patient_id,
            "dentist_id": plan.dentist_id,
            "title": plan.title,
            "notes": plan.notes,
            "items": [{f: getattr(i, f) for f in ITEM_FIELDS} for i in plan_items(db, plan)],
        },
    )
    return copy


# ---------- execução ----------


def _refresh_plan_status(db: Session, plan: TreatmentPlan) -> None:
    if plan.status is not PlanStatus.APROVADO:
        return
    new = regras.plan_after_items(i.status for i in plan_items(db, plan))
    if new is PlanStatus.CONCLUIDO:
        plan.status = new
    elif new is PlanStatus.CANCELADO:
        plan.status = new
        plan.cancelled_at = now()
        plan.cancel_reason = "Todos os itens aprovados foram cancelados."


def _odontogram_events(db: Session, item: TreatmentPlanItem) -> list[dict[str, Any]]:
    """Ao realizar: tira o 'a fazer' e marca o 'feito', onde fizer sentido."""
    if item.tooth is None or (item.planned_status_id is None and item.done_status_id is None):
        return []
    patient = get_patient(db, item.patient_id)
    current = odonto_service.current_marks(db, patient)
    events = []
    for status_id, action in (
        (item.planned_status_id, EventAction.REMOVER),
        (item.done_status_id, EventAction.MARCAR),
    ):
        if status_id is None:
            continue
        status = db.get(ToothStatus, status_id)
        if status is None:
            continue
        if action is EventAction.MARCAR and not status.active:
            continue
        faces = list(item.faces or "") if status.scope is StatusScope.FACE else [None]
        for face in faces:
            marked = (item.tooth, face, status_id) in current
            if (action is EventAction.REMOVER) == marked:
                events.append(
                    {"tooth": item.tooth, "face": face, "status_id": status_id,
                     "action": action, "notes": None}
                )  # fmt: skip
    return events


def perform_item(
    db: Session,
    user: CurrentUser,
    plan: TreatmentPlan,
    item: TreatmentPlanItem,
    encounter_id: uuid.UUID,
) -> int:
    """Marca o item como realizado no atendimento. Devolve quantos eventos foram para o
    odontograma."""
    if item.status is not ItemStatus.APROVADO:
        raise RuleViolation("Só item aprovado é realizado.")
    # Trava o atendimento: um fechamento concorrente espera e é visto aqui.
    encounter = db.scalar(select(Encounter).where(Encounter.id == encounter_id).with_for_update())
    if encounter is None:
        raise NotFound("Atendimento não encontrado.")
    if encounter.patient_id != item.patient_id:
        raise RuleViolation("O atendimento é de outro paciente.")
    if encounter.status is not EncounterStatus.ABERTO:
        raise RuleViolation("O atendimento está fechado.")
    if encounter.dentist_id != user.user_id:
        raise Forbidden("Só o dentista do atendimento registra o procedimento realizado.")
    item.status = ItemStatus.REALIZADO
    item.encounter_id = encounter.id
    item.performed_by = user.user_id
    item.performed_at = now()
    db.flush()
    events = _odontogram_events(db, item)
    if events:
        try:
            odonto_service.record_events(
                db, user, get_patient(db, item.patient_id), encounter.id, events
            )
        except odonto_service.OdontogramError as exc:
            raise RuleViolation(f"Odontograma: {exc.message}") from None
    _refresh_plan_status(db, plan)
    db.flush()
    return len(events)


def cancel_item(db: Session, plan: TreatmentPlan, item: TreatmentPlanItem, reason: str) -> None:
    if item.status is not ItemStatus.APROVADO:
        raise RuleViolation("Só item aprovado e ainda não realizado é cancelado.")
    item.status = ItemStatus.CANCELADO
    item.cancel_reason = reason
    db.flush()
    _refresh_plan_status(db, plan)
    db.flush()


def count_items(db: Session, plan_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not plan_ids:
        return {}
    rows = db.execute(
        select(TreatmentPlanItem.plan_id, func.count())
        .where(TreatmentPlanItem.plan_id.in_(plan_ids))
        .group_by(TreatmentPlanItem.plan_id)
    )
    return dict(rows.all())
