"""Financeiro: contas a receber, recebimentos e contas a pagar.

- `receivables`: uma parcela a receber de um paciente (entrada, parcela n/N ou avulsa),
  opcionalmente ligada a um plano de tratamento aprovado. O status (aberta, parcial, paga,
  vencida) é calculado pelos recebimentos; só o cancelamento é gravado.
- `payments`: recebimentos, append-only. Pagamento parcial é permitido; correção é um
  estorno (linha com valor negativo e `reversal_of`), nunca edição. A taxa do cartão é
  informada no registro (`fee_pct`), e o líquido fica gravado.
- `payables`: contas a pagar da clínica (fornecedor, categoria, vencimento), pagas de uma
  vez ou canceladas.

Gatilhos da migração 0014: o total recebido de uma parcela fica entre zero e o valor dela;
parcela cancelada não recebe; estorno anula exatamente um recebimento; parcela com
recebimento não muda valor, vencimento nem paciente, e só é cancelada com saldo zero.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class PaymentMethod(StrEnum):
    DINHEIRO = "dinheiro"
    PIX = "pix"
    DEBITO = "debito"
    CREDITO = "credito"
    BOLETO = "boleto"
    TRANSFERENCIA = "transferencia"


class ReceivableKind(StrEnum):
    ENTRADA = "entrada"
    PARCELA = "parcela"
    AVULSA = "avulsa"


class PayableStatus(StrEnum):
    ABERTA = "aberta"
    PAGA = "paga"
    CANCELADA = "cancelada"


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(
        e,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class Receivable(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "receivables"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_receivables_id_clinic"),
        UniqueConstraint("id", "patient_id", "clinic_id", name="uq_receivables_id_patient"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_receivables_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        # Plano (opcional) do mesmo paciente.
        ForeignKeyConstraint(
            ["plan_id", "patient_id", "clinic_id"],
            ["treatment_plans.id", "treatment_plans.patient_id", "treatment_plans.clinic_id"],
            name="fk_receivables_plan_same_patient",
            ondelete="RESTRICT",
        ),
        Index("ix_receivables_due", "clinic_id", "due_date"),
        Index("ix_receivables_patient", "patient_id", "due_date"),
        Index("ix_receivables_plan", "plan_id"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    plan_id: Mapped[uuid.UUID | None] = mapped_column()
    kind: Mapped[ReceivableKind] = mapped_column(_enum(ReceivableKind))
    description: Mapped[str] = mapped_column(String(200))
    installment_number: Mapped[int | None] = mapped_column(SmallInteger)
    installment_count: Mapped[int | None] = mapped_column(SmallInteger)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class Payment(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("id", "receivable_id", "clinic_id", name="uq_payments_id_receivable"),
        ForeignKeyConstraint(
            ["receivable_id", "patient_id", "clinic_id"],
            ["receivables.id", "receivables.patient_id", "receivables.clinic_id"],
            name="fk_payments_receivable_same_patient",
            ondelete="RESTRICT",
        ),
        # Estorno: do mesmo recebível; no máximo um por recebimento.
        ForeignKeyConstraint(
            ["reversal_of", "receivable_id", "clinic_id"],
            ["payments.id", "payments.receivable_id", "payments.clinic_id"],
            name="fk_payments_reversal_same_receivable",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_payments_one_reversal",
            "reversal_of",
            unique=True,
            postgresql_where=text("reversal_of IS NOT NULL"),
        ),
        Index("ix_payments_receivable", "receivable_id"),
        Index("ix_payments_paid_on", "clinic_id", "paid_on"),
    )

    receivable_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # negativo no estorno
    method: Mapped[PaymentMethod] = mapped_column(_enum(PaymentMethod))
    fee_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_on: Mapped[date] = mapped_column(Date)
    reversal_of: Mapped[uuid.UUID | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String(300))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payable(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payables"
    __table_args__ = (Index("ix_payables_due", "clinic_id", "due_date"),)

    supplier: Mapped[str] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(String(300))
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[PayableStatus] = mapped_column(
        _enum(PayableStatus),
        default=PayableStatus.ABERTA,
        server_default=PayableStatus.ABERTA.value,
    )
    paid_on: Mapped[date | None] = mapped_column(Date)
    paid_method: Mapped[PaymentMethod | None] = mapped_column(_enum(PaymentMethod))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
