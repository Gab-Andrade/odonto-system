"""Painel do gestor v1: indicadores agregados, só leitura, sem tabelas próprias.

Tudo roda na sessão de tenant (RLS), em SQL agregado. Nenhum indicador expõe dado
individual de paciente: para ver um paciente, abre-se o prontuário (que é auditado).
Cada número diz de onde vem (ver `schemas.py`).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.agenda.models import Appointment, AppointmentStatus, EntryKind
from app.modules.estoque import lotes_service as stock
from app.modules.estoque import regras as stock_rules
from app.modules.financeiro import regras as fin_rules
from app.modules.financeiro.models import Payable, PayableStatus, Payment, Receivable
from app.modules.prontuario.models import Encounter
from app.modules.repasse.models import CommissionSettlement
from app.modules.tratamento.models import ItemStatus, PlanStatus, TreatmentPlan, TreatmentPlanItem

STALE_QUOTE_DAYS = 7
PAYABLES_SOON_DAYS = 7


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def today() -> date:
    return datetime.now(tz()).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz())
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def month_bounds(month: date) -> tuple[date, date]:
    """Primeiro dia do mês e primeiro dia do mês seguinte."""
    first = month.replace(day=1)
    nxt = fin_rules.add_months(first, 1)
    return first, nxt


def _instant(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz()).astimezone(UTC)


def _money(value) -> Decimal:
    return fin_rules.money(Decimal(value or 0))


# ---------- agenda ----------


@dataclass
class AgendaDay:
    total: int
    agendado: int
    confirmado: int
    atendido: int
    falta: int
    cancelado: int


def agenda_day(db: Session, day: date, dentist_id: uuid.UUID | None = None) -> AgendaDay:
    start, end = day_bounds(day)
    query = select(Appointment.status, func.count()).where(
        Appointment.kind == EntryKind.CONSULTA,
        Appointment.starts_at >= start,
        Appointment.starts_at < end,
    )
    if dentist_id is not None:
        query = query.where(Appointment.dentist_id == dentist_id)
    counts = {status: n for status, n in db.execute(query.group_by(Appointment.status)).all()}
    S = AppointmentStatus
    return AgendaDay(
        total=sum(counts.values()),
        agendado=counts.get(S.AGENDADO, 0),
        confirmado=counts.get(S.CONFIRMADO, 0),
        atendido=counts.get(S.ATENDIDO, 0),
        falta=counts.get(S.FALTA, 0),
        cancelado=counts.get(S.CANCELADO, 0),
    )


# ---------- financeiro ----------


@dataclass
class Revenue:
    received: Decimal  # recebido no mês (bruto, já com estornos)
    received_net: Decimal  # menos taxas de cartão
    expected: Decimal  # contas a receber com vencimento no mês (não canceladas)


def revenue(db: Session, month: date) -> Revenue:
    first, nxt = month_bounds(month)
    received, net = db.execute(
        select(func.sum(Payment.amount), func.sum(Payment.net_amount)).where(
            Payment.paid_on >= first, Payment.paid_on < nxt
        )
    ).one()
    expected = db.scalar(
        select(func.sum(Receivable.amount)).where(
            Receivable.due_date >= first,
            Receivable.due_date < nxt,
            Receivable.cancelled_at.is_(None),
        )
    )
    return Revenue(_money(received), _money(net), _money(expected))


@dataclass
class Overdue:
    count: int
    amount: Decimal


def overdue_receivables(db: Session, day: date) -> Overdue:
    paid = (
        select(Payment.receivable_id, func.sum(Payment.amount).label("paid"))
        .group_by(Payment.receivable_id)
        .subquery()
    )
    balance = Receivable.amount - func.coalesce(paid.c.paid, 0)
    count, amount = db.execute(
        select(func.count(), func.sum(balance))
        .select_from(Receivable)
        .outerjoin(paid, paid.c.receivable_id == Receivable.id)
        .where(Receivable.cancelled_at.is_(None), Receivable.due_date < day, balance > 0)
    ).one()
    return Overdue(count or 0, _money(amount))


@dataclass
class Payables:
    overdue_count: int
    overdue_amount: Decimal
    soon_count: int
    soon_amount: Decimal


def payables(db: Session, day: date) -> Payables:
    soon = day + timedelta(days=PAYABLES_SOON_DAYS)
    is_overdue = Payable.due_date < day
    is_soon = and_(Payable.due_date >= day, Payable.due_date <= soon)
    row = db.execute(
        select(
            func.count(case((is_overdue, 1))),
            func.sum(case((is_overdue, Payable.amount))),
            func.count(case((is_soon, 1))),
            func.sum(case((is_soon, Payable.amount))),
        ).where(Payable.status == PayableStatus.ABERTA)
    ).one()
    return Payables(row[0] or 0, _money(row[1]), row[2] or 0, _money(row[3]))


# ---------- orçamentos ----------


@dataclass
class Quotes:
    awaiting: int  # emitidos, sem decisão
    awaiting_stale: int  # emitidos há mais de N dias
    issued_in_month: int
    approved_in_month: int  # decididos no mês com ao menos um item aprovado
    approved_value_in_month: Decimal  # soma dos itens aprovados (antes do desconto)


def quotes(db: Session, month: date, day: date, dentist_id: uuid.UUID | None = None) -> Quotes:
    first, nxt = month_bounds(month)
    base = select(TreatmentPlan)
    if dentist_id is not None:
        base = base.where(TreatmentPlan.dentist_id == dentist_id)
    sub = base.subquery()
    stale_limit = _instant(day - timedelta(days=STALE_QUOTE_DAYS))
    awaiting, stale, issued = db.execute(
        select(
            func.count(case((sub.c.status == PlanStatus.EMITIDO.value, 1))),
            func.count(
                case(
                    (
                        and_(
                            sub.c.status == PlanStatus.EMITIDO.value,
                            sub.c.issued_at < stale_limit,
                        ),
                        1,
                    )
                )
            ),
            func.count(
                case((and_(sub.c.issued_at >= _instant(first), sub.c.issued_at < _instant(nxt)), 1))
            ),
        ).select_from(sub)
    ).one()
    approved_statuses = (PlanStatus.APROVADO, PlanStatus.CONCLUIDO)
    decided = and_(
        TreatmentPlan.decided_at >= _instant(first),
        TreatmentPlan.decided_at < _instant(nxt),
        TreatmentPlan.status.in_(approved_statuses),
    )
    plans_q = select(func.count()).select_from(TreatmentPlan).where(decided)
    value_q = (
        select(func.sum(TreatmentPlanItem.unit_price))
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .where(decided, TreatmentPlanItem.status.in_((ItemStatus.APROVADO, ItemStatus.REALIZADO)))
    )
    if dentist_id is not None:
        plans_q = plans_q.where(TreatmentPlan.dentist_id == dentist_id)
        value_q = value_q.where(TreatmentPlan.dentist_id == dentist_id)
    return Quotes(
        awaiting or 0,
        stale or 0,
        issued or 0,
        db.scalar(plans_q) or 0,
        _money(db.scalar(value_q)),
    )


# ---------- produção ----------


@dataclass
class Production:
    dentist_id: uuid.UUID
    procedures: int
    value: Decimal  # valor dos itens realizados, com o desconto do plano


def production(db: Session, month: date, dentist_id: uuid.UUID | None = None) -> list[Production]:
    first, nxt = month_bounds(month)
    net = TreatmentPlanItem.unit_price * (1 - TreatmentPlan.discount_pct / 100)
    query = (
        select(TreatmentPlanItem.performed_by, func.count(), func.sum(net))
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .where(
            TreatmentPlanItem.status == ItemStatus.REALIZADO,
            TreatmentPlanItem.performed_at >= _instant(first),
            TreatmentPlanItem.performed_at < _instant(nxt),
        )
        .group_by(TreatmentPlanItem.performed_by)
    )
    if dentist_id is not None:
        query = query.where(TreatmentPlanItem.performed_by == dentist_id)
    return [Production(d, n, _money(v)) for d, n, v in db.execute(query).all()]


def encounters_in_month(db: Session, month: date, dentist_id: uuid.UUID) -> int:
    first, nxt = month_bounds(month)
    return (
        db.scalar(
            select(func.count()).where(
                Encounter.dentist_id == dentist_id,
                Encounter.started_at >= _instant(first),
                Encounter.started_at < _instant(nxt),
            )
        )
        or 0
    )


def last_settlement(db: Session, dentist_id: uuid.UUID) -> CommissionSettlement | None:
    return db.scalar(
        select(CommissionSettlement)
        .where(CommissionSettlement.dentist_id == dentist_id)
        .order_by(CommissionSettlement.period_end.desc())
        .limit(1)
    )


# ---------- estoque ----------


@dataclass
class StockAlerts:
    below_minimum: int
    expired_lots: int  # lotes vencidos com saldo
    expiring_lots: int  # vencem em até 30 dias


def stock_alerts(db: Session, day: date) -> StockAlerts:
    below = expired = expiring = 0
    for row in stock.stock(db):
        if row.below_minimum:
            below += 1
        for lot, balance in row.lots:
            if balance <= 0:
                continue
            status = stock_rules.expiry_status(lot.expires_on, day)
            if status == "vencido":
                expired += 1
            elif status == "vence_em_breve":
                expiring += 1
    return StockAlerts(below, expired, expiring)
