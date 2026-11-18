"""Regras do financeiro. O commit e a auditoria ficam com o router."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.modules.financeiro import regras
from app.modules.financeiro.models import (
    FinancialSettings,
    Payable,
    PayableStatus,
    Payment,
    PaymentMethod,
    Receivable,
    ReceivableKind,
)
from app.modules.pacientes import service as pacientes_service
from app.modules.pacientes.models import Patient
from app.modules.tratamento import regras as plan_rules
from app.modules.tratamento import service as plan_service
from app.modules.tratamento.models import PlanStatus

MAX_LIST = 500


class FinanceError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(FinanceError):
    pass


class RuleViolation(FinanceError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def _rule(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except regras.FinanceRuleError as exc:
        raise RuleViolation(str(exc)) from None


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    try:
        return pacientes_service.get_patient(db, patient_id)
    except pacientes_service.NotFound as exc:
        raise NotFound(exc.message) from None


# ---------- contas a receber ----------


@dataclass
class ReceivableRow:
    receivable: Receivable
    paid: Decimal
    status: str

    @property
    def balance(self) -> Decimal:
        if self.receivable.cancelled_at is not None:
            return regras.money(Decimal("0"))
        return regras.money(self.receivable.amount - self.paid)


def _paid_by(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not ids:
        return {}
    rows = db.execute(
        select(Payment.receivable_id, func.sum(Payment.amount))
        .where(Payment.receivable_id.in_(ids))
        .group_by(Payment.receivable_id)
    )
    return {rid: total for rid, total in rows.all()}


def rows_for(db: Session, receivables: list[Receivable]) -> list[ReceivableRow]:
    paid = _paid_by(db, [r.id for r in receivables])
    day = today()
    result = []
    for r in receivables:
        p = regras.money(paid.get(r.id, Decimal("0")))
        status = regras.receivable_status(r.amount, p, r.due_date, day, r.cancelled_at is not None)
        result.append(ReceivableRow(r, p, status))
    return result


def get_receivable(db: Session, receivable_id: uuid.UUID, *, lock: bool = False) -> Receivable:
    query = select(Receivable).where(Receivable.id == receivable_id)
    if lock:
        query = query.with_for_update()
    receivable = db.scalar(query)
    if receivable is None:  # de outra clínica também cai aqui (RLS)
        raise NotFound("Conta a receber não encontrada.")
    return receivable


def list_receivables(
    db: Session,
    *,
    patient_id: uuid.UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    include_cancelled: bool = False,
    limit: int | None = 200,
) -> list[ReceivableRow]:
    """`limit=None` só para consultas de um paciente (extrato), que precisam de tudo."""
    query = select(Receivable).order_by(Receivable.due_date, Receivable.installment_number)
    if patient_id is not None:
        query = query.where(Receivable.patient_id == patient_id)
    if due_from is not None:
        query = query.where(Receivable.due_date >= due_from)
    if due_to is not None:
        query = query.where(Receivable.due_date <= due_to)
    if not include_cancelled:
        query = query.where(Receivable.cancelled_at.is_(None))
    if limit is not None:
        query = query.limit(min(limit, MAX_LIST))
    return rows_for(db, list(db.scalars(query)))


def create_receivable(db: Session, user: CurrentUser, data: dict) -> Receivable:
    patient = get_patient(db, data["patient_id"])
    receivable = Receivable(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        kind=ReceivableKind.AVULSA,
        description=data["description"],
        due_date=data["due_date"],
        amount=regras.money(data["amount"]),
        created_by=user.user_id,
    )
    db.add(receivable)
    db.flush()
    return receivable


def installment_plan(
    db: Session,
    user: CurrentUser,
    plan_id: uuid.UUID,
    down_payment: Decimal,
    installments: int,
    down_payment_date: date | None,
    first_due_date: date | None,
) -> list[Receivable]:
    """Gera as contas a receber do orçamento aprovado: entrada + parcelas mensais."""
    try:
        plan = plan_service.get_plan(db, plan_id, lock=True)
    except plan_service.NotFound as exc:
        raise NotFound(exc.message) from None
    if plan.status not in (PlanStatus.APROVADO, PlanStatus.CONCLUIDO):
        raise RuleViolation("Só orçamento aprovado é parcelado.")
    existing = select(Receivable.id).where(
        Receivable.plan_id == plan.id, Receivable.cancelled_at.is_(None)
    )
    if db.scalar(existing.limit(1)) is not None:
        raise RuleViolation("Este orçamento já foi parcelado; cancele o parcelamento antes.")
    items = plan_service.plan_items(db, plan)
    total = plan_rules.totals(((i.status, i.unit_price) for i in items), plan.discount_pct)
    start = down_payment_date or today()
    first = first_due_date or regras.add_months(start, 1)
    parts = _rule(
        regras.split,
        total.approved_total,
        down_payment=down_payment,
        installments=installments,
        down_payment_date=start,
        first_due_date=first,
    )
    label = plan.title or "Plano de tratamento"
    rows = []
    for part in parts:
        if part.kind == "entrada":
            description = f"{label} — entrada"
        else:
            description = f"{label} — parcela {part.number}/{part.count}"
        rows.append(
            Receivable(
                clinic_id=user.clinic_id,
                patient_id=plan.patient_id,
                plan_id=plan.id,
                kind=ReceivableKind(part.kind),
                description=description,
                installment_number=part.number,
                installment_count=part.count,
                due_date=part.due_date,
                amount=part.amount,
                created_by=user.user_id,
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def cancel_receivable(db: Session, receivable: Receivable, reason: str) -> None:
    if receivable.cancelled_at is not None:
        raise RuleViolation("Conta já cancelada.")
    if _paid_by(db, [receivable.id]).get(receivable.id, Decimal("0")) != 0:
        raise RuleViolation("Conta com recebimento: estorne antes de cancelar.")
    receivable.cancelled_at = now()
    receivable.cancel_reason = reason
    db.flush()


def cancel_plan_installments(db: Session, plan_id: uuid.UUID, reason: str) -> int:
    """Cancela o parcelamento do orçamento (todas as contas sem recebimento)."""
    rows = list(
        db.scalars(
            select(Receivable)
            .where(Receivable.plan_id == plan_id, Receivable.cancelled_at.is_(None))
            .with_for_update()
        )
    )
    if not rows:
        raise NotFound("Parcelamento não encontrado para este orçamento.")
    paid = _paid_by(db, [r.id for r in rows])
    if any(paid.get(r.id, Decimal("0")) != 0 for r in rows):
        raise RuleViolation("Há parcela com recebimento: estorne antes de refazer o parcelamento.")
    for r in rows:
        r.cancelled_at = now()
        r.cancel_reason = reason
    db.flush()
    return len(rows)


# ---------- recebimentos ----------


def get_payment(db: Session, payment_id: uuid.UUID) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFound("Recebimento não encontrado.")
    return payment


def list_payments(db: Session, receivable_ids: list[uuid.UUID]) -> list[Payment]:
    if not receivable_ids:
        return []
    query = (
        select(Payment)
        .where(Payment.receivable_id.in_(receivable_ids))
        .order_by(Payment.paid_on, Payment.created_at)
    )
    return list(db.scalars(query))


def _check_paid_on(paid_on: date | None) -> date:
    day = paid_on or today()
    if day > today():
        raise RuleViolation("A data do recebimento não pode ser futura.")
    return day


def register_payment(
    db: Session,
    user: CurrentUser,
    receivable: Receivable,
    amount: Decimal,
    method: PaymentMethod,
    fee_pct: Decimal,
    paid_on: date | None,
    notes: str | None,
) -> Payment:
    """Recebimento (total ou parcial) de uma conta. A conta deve vir travada."""
    if receivable.cancelled_at is not None:
        raise RuleViolation("Conta cancelada não recebe pagamento.")
    paid = _paid_by(db, [receivable.id]).get(receivable.id, Decimal("0"))
    if amount > receivable.amount - paid:
        raise RuleViolation(f"Valor acima do saldo da conta ({receivable.amount - paid}).")
    fee_amount, net = _rule(regras.fee, amount, fee_pct)
    amount = regras.money(amount)
    payment = Payment(
        clinic_id=user.clinic_id,
        receivable_id=receivable.id,
        patient_id=receivable.patient_id,
        amount=amount,
        method=method,
        fee_pct=fee_pct,
        fee_amount=fee_amount,
        net_amount=net,
        paid_on=_check_paid_on(paid_on),
        notes=notes,
        recorded_by=user.user_id,
    )
    db.add(payment)
    db.flush()
    db.refresh(payment)
    return payment


def reverse_payment(db: Session, user: CurrentUser, payment: Payment, reason: str) -> Payment:
    """Estorno: lançamento negativo que anula o recebimento (o original continua)."""
    if payment.reversal_of is not None:
        raise RuleViolation("Estorno não é estornado.")
    taken = select(Payment.id).where(Payment.reversal_of == payment.id)
    if db.scalar(taken.limit(1)) is not None:
        raise RuleViolation("Este recebimento já foi estornado.")
    reversal = Payment(
        clinic_id=user.clinic_id,
        receivable_id=payment.receivable_id,
        patient_id=payment.patient_id,
        amount=-payment.amount,
        method=payment.method,
        fee_pct=payment.fee_pct,
        fee_amount=-payment.fee_amount,
        net_amount=-payment.net_amount,
        paid_on=today(),
        reversal_of=payment.id,
        notes=reason,
        recorded_by=user.user_id,
    )
    db.add(reversal)
    db.flush()
    db.refresh(reversal)
    return reversal


@dataclass
class Statement:
    receivables: list[ReceivableRow]
    payments: list[Payment]

    @property
    def total(self) -> Decimal:
        open_ = (r.receivable.amount for r in self.receivables if r.receivable.cancelled_at is None)
        return regras.money(sum(open_, Decimal("0")))

    @property
    def paid(self) -> Decimal:
        return regras.money(sum((p.amount for p in self.payments), Decimal("0")))

    @property
    def overdue(self) -> Decimal:
        late = (r.balance for r in self.receivables if r.status == "vencida")
        return regras.money(sum(late, Decimal("0")))


def statement(db: Session, patient: Patient) -> Statement:
    rows = list_receivables(db, patient_id=patient.id, include_cancelled=True, limit=None)
    return Statement(rows, list_payments(db, [r.receivable.id for r in rows]))


# ---------- contas a pagar ----------


def get_payable(db: Session, payable_id: uuid.UUID) -> Payable:
    payable = db.scalar(select(Payable).where(Payable.id == payable_id).with_for_update())
    if payable is None:
        raise NotFound("Conta a pagar não encontrada.")
    return payable


def list_payables(
    db: Session,
    *,
    due_from: date | None = None,
    due_to: date | None = None,
    status: PayableStatus | None = None,
    limit: int = 200,
) -> list[Payable]:
    query = select(Payable).order_by(Payable.due_date, Payable.created_at)
    if due_from is not None:
        query = query.where(Payable.due_date >= due_from)
    if due_to is not None:
        query = query.where(Payable.due_date <= due_to)
    if status is not None:
        query = query.where(Payable.status == status)
    return list(db.scalars(query.limit(min(limit, MAX_LIST))))


def create_payable(db: Session, user: CurrentUser, data: dict) -> Payable:
    data = {**data, "amount": regras.money(data["amount"])}
    payable = Payable(clinic_id=user.clinic_id, created_by=user.user_id, **data)
    db.add(payable)
    db.flush()
    return payable


def pay_payable(db: Session, payable: Payable, method: PaymentMethod, paid_on: date | None):
    if payable.status is not PayableStatus.ABERTA:
        raise RuleViolation("Só conta em aberto é paga.")
    payable.status = PayableStatus.PAGA
    payable.paid_method = method
    payable.paid_on = _check_paid_on(paid_on)
    db.flush()


def cancel_payable(db: Session, payable: Payable, reason: str) -> None:
    if payable.status is not PayableStatus.ABERTA:
        raise RuleViolation("Só conta em aberto é cancelada.")
    payable.status = PayableStatus.CANCELADA
    payable.cancel_reason = reason
    db.flush()


# ---------- configuração ----------


def dentist_can_view(db: Session) -> bool:
    row = db.scalar(select(FinancialSettings))
    return bool(row and row.dentist_can_view)


def save_settings(db: Session, user: CurrentUser, dentist_view: bool) -> bool:
    """Grava a configuração; devolve se mudou (para a auditoria)."""
    before = dentist_can_view(db)
    stmt = insert(FinancialSettings).values(
        id=uuid.uuid4(),
        clinic_id=user.clinic_id,
        dentist_can_view=dentist_view,
        updated_by=user.user_id,
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["clinic_id"],
            set_={
                "dentist_can_view": dentist_view,
                "updated_by": user.user_id,
                "updated_at": now(),
            },
        )
    )
    db.flush()
    return before != dentist_view
