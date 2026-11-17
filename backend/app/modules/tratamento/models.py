"""Plano de tratamento e orçamento.

O plano e o orçamento são a mesma entidade em fases diferentes:

    rascunho ──emitir──▶ emitido ──decisão──▶ aprovado ──(todos feitos)──▶ concluído
       │                    │          └────▶ recusado
       └──cancelar──────────┴──▶ cancelado

- `treatment_plans`: um por proposta ao paciente, com dentista responsável (cuja tabela de
  preço é usada), desconto percentual sobre o total e validade.
- `treatment_plan_items`: procedimento, dente e faces. Ao emitir, cada item ganha o preço
  congelado (`price_snapshots` da precificação, com tabela, versão e memória de cálculo).
  Itens: proposto → aprovado/recusado (aprovação parcial) → realizado/cancelado.
  O item pode apontar itens da legenda do odontograma: `planned_status_id` (o "a fazer")
  e `done_status_id` (o "feito"); ao realizar, o odontograma é atualizado.
- `treatment_settings`: por clínica, validade padrão do orçamento e desconto máximo que
  dentista e recepção podem dar (admin e gestor não têm limite).

Gatilhos da migração 0013: preço congelado e desconto não mudam depois de emitido; item só
é apagado com o plano em rascunho. Plano não se apaga (só cancela).
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
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin

DEFAULT_VALIDITY_DAYS = 30
DEFAULT_MAX_DISCOUNT_PCT = Decimal("5.00")


class PlanStatus(StrEnum):
    RASCUNHO = "rascunho"
    EMITIDO = "emitido"
    APROVADO = "aprovado"
    RECUSADO = "recusado"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"


class ItemStatus(StrEnum):
    PROPOSTO = "proposto"
    APROVADO = "aprovado"
    RECUSADO = "recusado"
    REALIZADO = "realizado"
    CANCELADO = "cancelado"


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(
        e,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class TreatmentSettings(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "treatment_settings"
    __table_args__ = (UniqueConstraint("clinic_id", name="uq_treatment_settings_clinic"),)

    validity_days: Mapped[int] = mapped_column(Integer)
    max_discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class TreatmentPlan(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "treatment_plans"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_treatment_plans_id_clinic"),
        UniqueConstraint("id", "patient_id", "clinic_id", name="uq_treatment_plans_id_patient"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_treatment_plans_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_treatment_plans_patient", "patient_id", "created_at"),
        Index("ix_treatment_plans_status", "clinic_id", "status"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    # Responsável: vínculo ativo de dentista ou admin (validado no service).
    dentist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus), default=PlanStatus.RASCUNHO, server_default=PlanStatus.RASCUNHO.value
    )
    title: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(String(2000))
    discount_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), server_default="0"
    )
    valid_until: Mapped[date | None] = mapped_column(Date)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class TreatmentPlanItem(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "treatment_plan_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id", "patient_id", "clinic_id"],
            ["treatment_plans.id", "treatment_plans.patient_id", "treatment_plans.clinic_id"],
            name="fk_treatment_plan_items_plan_same_patient",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["price_snapshot_id", "clinic_id"],
            ["price_snapshots.id", "price_snapshots.clinic_id"],
            name="fk_treatment_plan_items_snapshot_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["planned_status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_treatment_plan_items_planned_status_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["done_status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_treatment_plan_items_done_status_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_treatment_plan_items_encounter_same_patient",
            ondelete="RESTRICT",
        ),
        Index("ix_treatment_plan_items_plan", "plan_id", "sort_order"),
        Index("ix_treatment_plan_items_performed", "clinic_id", "performed_at"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    procedure_code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(String(300))  # do preço, ao emitir
    tooth: Mapped[int | None] = mapped_column(SmallInteger)
    faces: Mapped[str | None] = mapped_column(String(5))  # ex.: "MOD"
    notes: Mapped[str | None] = mapped_column(String(500))
    planned_status_id: Mapped[uuid.UUID | None] = mapped_column()
    done_status_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[ItemStatus] = mapped_column(
        _enum(ItemStatus), default=ItemStatus.PROPOSTO, server_default=ItemStatus.PROPOSTO.value
    )
    price_snapshot_id: Mapped[uuid.UUID | None] = mapped_column()
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
