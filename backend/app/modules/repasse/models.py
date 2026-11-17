"""Repasse (comissão) de dentistas.

- `commission_rules`: regra por dentista — percentual ou valor fixo —, opcionalmente só para
  um procedimento (exceção à regra geral do dentista), com vigência a partir de uma data e
  descontos opcionais (custo dos materiais consumidos e taxa de cartão). Append-only: mudar
  a regra é criar outra com vigência nova; vale a de vigência mais recente até a data em
  que o procedimento foi realizado.
- `commission_settlements` + `commission_lines`: fechamento por dentista até uma data,
  append-only. A base é o que o paciente pagou do plano, rateado entre os itens realizados
  (repasse sobre o recebido). O cálculo é acumulado: cada fechamento leva só a diferença
  em relação ao que já foi repassado por item, então pagamentos novos entram no próximo e
  um estorno depois do fechamento gera linha negativa.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, UUIDPkMixin


class RuleKind(StrEnum):
    PERCENTUAL = "percentual"
    FIXO = "fixo"


class CommissionRule(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "commission_rules"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_commission_rules_id_clinic"),
        Index("ix_commission_rules_lookup", "dentist_id", "procedure_code", "valid_from"),
    )

    dentist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    procedure_code: Mapped[str | None] = mapped_column(String(40))  # None = regra geral
    kind: Mapped[RuleKind] = mapped_column(
        Enum(
            RuleKind,
            native_enum=False,
            length=20,
            values_callable=lambda x: [m.value for m in x],
            validate_strings=True,
            create_constraint=False,  # o CHECK é criado na migração
        )
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # % ou R$ por procedimento
    deduct_materials: Mapped[bool] = mapped_column(Boolean, default=False)
    deduct_card_fee: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommissionSettlement(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "commission_settlements"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_commission_settlements_id_clinic"),
        UniqueConstraint(
            "clinic_id", "dentist_id", "period_end", name="uq_commission_settlements_dentist_end"
        ),
    )

    dentist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    period_start: Mapped[date | None] = mapped_column(Date)  # dia seguinte ao anterior
    period_end: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(String(300))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommissionLine(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "commission_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["settlement_id", "clinic_id"],
            ["commission_settlements.id", "commission_settlements.clinic_id"],
            name="fk_commission_lines_settlement_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_item_id", "clinic_id"],
            ["treatment_plan_items.id", "treatment_plan_items.clinic_id"],
            name="fk_commission_lines_plan_item_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rule_id", "clinic_id"],
            ["commission_rules.id", "commission_rules.clinic_id"],
            name="fk_commission_lines_rule_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_commission_lines_item", "plan_item_id"),
        Index("ix_commission_lines_settlement", "settlement_id"),
    )

    settlement_id: Mapped[uuid.UUID] = mapped_column()
    plan_item_id: Mapped[uuid.UUID] = mapped_column()
    procedure_code: Mapped[str] = mapped_column(String(40))
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # recebido rateado
    fee_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    material_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    rule_id: Mapped[uuid.UUID] = mapped_column()
    commission: Mapped[Decimal] = mapped_column(Numeric(12, 2))
