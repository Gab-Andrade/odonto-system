import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.financeiro import regras
from app.modules.financeiro.models import PayableStatus, PaymentMethod, ReceivableKind


def _text(max_length: int):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)
    ]


Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Pct = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class InstallmentPlanIn(BaseModel):
    down_payment: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] = Decimal("0")
    installments: int = Field(0, ge=0, le=regras.MAX_INSTALLMENTS)
    down_payment_date: date | None = Field(None, description="Padrão: hoje.")
    first_due_date: date | None = Field(None, description="Padrão: um mês depois da entrada.")


class ReceivableCreate(BaseModel):
    """Conta avulsa (fora de orçamento)."""

    patient_id: uuid.UUID
    description: _text(200)
    due_date: date
    amount: Money


class ReceivableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    plan_id: uuid.UUID | None
    kind: ReceivableKind
    description: str
    installment_number: int | None
    installment_count: int | None
    due_date: date
    amount: Decimal
    paid: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    status: str = "aberta"
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime


class PaymentIn(BaseModel):
    amount: Money
    method: PaymentMethod
    fee_pct: Pct = Field(Decimal("0"), description="Taxa do cartão/boleto, se houver.")
    paid_on: date | None = Field(None, description="Padrão: hoje. Não pode ser futura.")
    notes: _text(300) | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    receivable_id: uuid.UUID
    patient_id: uuid.UUID
    amount: Decimal
    method: PaymentMethod
    fee_pct: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    paid_on: date
    reversal_of: uuid.UUID | None
    notes: str | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class ReasonIn(BaseModel):
    reason: _text(300)


class StatementOut(BaseModel):
    patient_id: uuid.UUID
    total: Decimal
    paid: Decimal
    balance: Decimal
    overdue: Decimal
    receivables: list[ReceivableOut]
    payments: list[PaymentOut]


class PayableCreate(BaseModel):
    supplier: _text(150)
    category: _text(80) | None = None
    description: _text(300) | None = None
    due_date: date
    amount: Money


class PayablePay(BaseModel):
    method: PaymentMethod
    paid_on: date | None = None


class PayableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier: str
    category: str | None
    description: str | None
    due_date: date
    amount: Decimal
    status: PayableStatus
    overdue: bool = False
    paid_on: date | None
    paid_method: PaymentMethod | None
    cancel_reason: str | None
    created_at: datetime
