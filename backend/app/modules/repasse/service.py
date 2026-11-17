"""Cálculo e fechamento do repasse. O commit e a auditoria ficam com o router."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.estoque.models import MovementKind, StockLot, StockMovement
from app.modules.financeiro.models import Payment, Receivable
from app.modules.identidade.service import active_role
from app.modules.repasse import regras
from app.modules.repasse.models import (
    CommissionLine,
    CommissionRule,
    CommissionSettlement,
)
from app.modules.tratamento import regras as plan_rules
from app.modules.tratamento.models import ItemStatus, TreatmentPlan, TreatmentPlanItem

DENTIST_ROLES = (Role.DENTISTA, Role.ADMIN)


class CommissionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(CommissionError):
    pass


class RuleViolation(CommissionError):
    pass


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def _local_date(moment: datetime) -> date:
    return moment.astimezone(ZoneInfo(get_settings().clinic_timezone)).date()


def ensure_dentist(db: Session, user: CurrentUser, dentist_id: uuid.UUID) -> None:
    if active_role(db, dentist_id, user.clinic_id) not in DENTIST_ROLES:
        raise RuleViolation("Dentista não encontrado na clínica.")


# ---------- regras ----------


def list_rules(db: Session, dentist_id: uuid.UUID | None = None) -> list[CommissionRule]:
    query = select(CommissionRule).order_by(
        CommissionRule.dentist_id, CommissionRule.procedure_code, CommissionRule.valid_from
    )
    if dentist_id is not None:
        query = query.where(CommissionRule.dentist_id == dentist_id)
    return list(db.scalars(query))


def create_rule(db: Session, user: CurrentUser, data: dict) -> CommissionRule:
    ensure_dentist(db, user, data["dentist_id"])
    if data["kind"] == "percentual" and data["value"] > 100:
        raise RuleViolation("Percentual entre 0 e 100.")
    rule = CommissionRule(
        clinic_id=user.clinic_id,
        created_by=user.user_id,
        **{**data, "valid_from": data.get("valid_from") or today()},
    )
    db.add(rule)
    db.flush()
    return rule


# ---------- cálculo ----------


@dataclass
class PreviewLine:
    item: TreatmentPlanItem
    rule: CommissionRule
    line: regras.Line


@dataclass
class Preview:
    dentist_id: uuid.UUID
    period_start: date | None
    period_end: date
    lines: list[PreviewLine] = field(default_factory=list)
    missing_rule: list[str] = field(default_factory=list)  # procedimentos sem regra

    @property
    def total(self) -> Decimal:
        return regras.money(sum((p.line.commission for p in self.lines), Decimal("0")))


def last_settlement(db: Session, dentist_id: uuid.UUID) -> CommissionSettlement | None:
    return db.scalar(
        select(CommissionSettlement)
        .where(CommissionSettlement.dentist_id == dentist_id)
        .order_by(CommissionSettlement.period_end.desc())
        .limit(1)
    )


def compute(db: Session, dentist_id: uuid.UUID, period_end: date) -> Preview:
    """Repasse do dentista acumulado até `period_end`, menos o já fechado."""
    previous = last_settlement(db, dentist_id)
    if previous is not None and period_end <= previous.period_end:
        raise RuleViolation(f"Já há fechamento até {previous.period_end}.")
    start = previous.period_end + timedelta(days=1) if previous else None
    preview = Preview(dentist_id, start, period_end)

    items = [
        (item, plan)
        for item, plan in db.execute(
            select(TreatmentPlanItem, TreatmentPlan)
            .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
            .where(
                TreatmentPlanItem.performed_by == dentist_id,
                TreatmentPlanItem.status == ItemStatus.REALIZADO,
            )
        ).all()
        if _local_date(item.performed_at) <= period_end
    ]
    if not items:
        return preview
    plan_ids = {plan.id for _, plan in items}
    item_ids = [item.id for item, _ in items]

    # Recebido (e taxas) de cada plano até a data.
    paid_rows = db.execute(
        select(Receivable.plan_id, func.sum(Payment.amount), func.sum(Payment.fee_amount))
        .join(Receivable, Receivable.id == Payment.receivable_id)
        .where(Receivable.plan_id.in_(plan_ids), Payment.paid_on <= period_end)
        .group_by(Receivable.plan_id)
    ).all()
    paid = {pid: (amount, fees) for pid, amount, fees in paid_rows}

    # Total aprovado de cada plano (itens aprovados e realizados, com desconto).
    plan_items: dict[uuid.UUID, list[TreatmentPlanItem]] = {pid: [] for pid in plan_ids}
    for it in db.scalars(select(TreatmentPlanItem).where(TreatmentPlanItem.plan_id.in_(plan_ids))):
        plan_items[it.plan_id].append(it)

    already = dict(
        db.execute(
            select(CommissionLine.plan_item_id, func.sum(CommissionLine.base_amount))
            .where(CommissionLine.plan_item_id.in_(item_ids))
            .group_by(CommissionLine.plan_item_id)
        ).all()
    )
    materials = dict(
        db.execute(
            select(
                StockMovement.plan_item_id,
                func.sum(-StockMovement.quantity * StockLot.unit_cost),
            )
            .join(StockLot, StockLot.id == StockMovement.lot_id)
            .where(
                StockMovement.plan_item_id.in_(item_ids),
                StockMovement.kind == MovementKind.CONSUMO,
            )
            .group_by(StockMovement.plan_item_id)
        ).all()
    )
    rules = [
        regras.Rule(
            r,
            r.procedure_code,
            r.kind.value,
            r.value,
            r.deduct_materials,
            r.deduct_card_fee,
            r.valid_from,
        )
        for r in list_rules(db, dentist_id)
    ]

    for item, plan in sorted(items, key=lambda x: x[0].performed_at):
        chosen = regras.pick_rule(rules, item.procedure_code, _local_date(item.performed_at))
        if chosen is None:
            if item.procedure_code not in preview.missing_rule:
                preview.missing_rule.append(item.procedure_code)
            continue
        totals = plan_rules.totals(
            ((i.status, i.unit_price) for i in plan_items[plan.id]), plan.discount_pct
        )
        amount, fees = paid.get(plan.id, (Decimal("0"), Decimal("0")))
        item_net = regras.money(item.unit_price * (1 - plan.discount_pct / 100))
        line = regras.compute_line(
            item_net=item_net,
            ratio=regras.paid_ratio(amount, totals.approved_total),
            already_based=already.get(item.id, Decimal("0")),
            fee_ratio=(fees / amount) if amount > 0 else Decimal("0"),
            material_cost=materials.get(item.id) or Decimal("0"),
            rule=chosen,
        )
        if line.base != 0:
            preview.lines.append(PreviewLine(item, chosen.key, line))
    return preview


def close(
    db: Session, user: CurrentUser, dentist_id: uuid.UUID, period_end: date, notes: str | None
) -> tuple[CommissionSettlement, Preview]:
    if period_end > today():
        raise RuleViolation("O fechamento vai até hoje, no máximo.")
    ensure_dentist(db, user, dentist_id)
    # Um fechamento por vez para o mesmo dentista (o cálculo depende do anterior).
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"repasse:{dentist_id}"))))
    preview = compute(db, dentist_id, period_end)
    settlement = CommissionSettlement(
        clinic_id=user.clinic_id,
        dentist_id=dentist_id,
        period_start=preview.period_start,
        period_end=period_end,
        total=preview.total,
        notes=notes,
        closed_by=user.user_id,
    )
    db.add(settlement)
    db.flush()
    db.add_all(
        CommissionLine(
            clinic_id=user.clinic_id,
            settlement_id=settlement.id,
            plan_item_id=p.item.id,
            procedure_code=p.item.procedure_code,
            base_amount=p.line.base,
            fee_deduction=p.line.fee_deduction,
            material_deduction=p.line.material_deduction,
            rule_id=p.rule.id,
            commission=p.line.commission,
        )
        for p in preview.lines
    )
    db.flush()
    db.refresh(settlement)
    return settlement, preview


def list_settlements(db: Session, dentist_id: uuid.UUID | None = None):
    query = select(CommissionSettlement).order_by(CommissionSettlement.period_end.desc())
    if dentist_id is not None:
        query = query.where(CommissionSettlement.dentist_id == dentist_id)
    return list(db.scalars(query))


def get_settlement(db: Session, settlement_id: uuid.UUID) -> CommissionSettlement:
    settlement = db.get(CommissionSettlement, settlement_id)
    if settlement is None:
        raise NotFound("Fechamento não encontrado.")
    return settlement


def settlement_lines(db: Session, settlement: CommissionSettlement) -> list[CommissionLine]:
    query = select(CommissionLine).where(CommissionLine.settlement_id == settlement.id)
    return list(db.scalars(query.order_by(CommissionLine.procedure_code)))
