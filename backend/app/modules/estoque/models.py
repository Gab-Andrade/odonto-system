"""Estoque: materiais, lotes com validade e movimentos.

- `materials`: cadastro com unidade de uso, custo unitário (média ponderada dos lotes em
  estoque, atualizada a cada entrada; alimenta a precificação por custo) e estoque mínimo.
  Material não é excluído, só desativado: fichas técnicas apontam para ele.
- `stock_lots`: cada entrada cria um lote (código do lote e validade opcionais, custo da
  compra, fornecedor). O saldo do lote é a soma dos movimentos dele.
- `stock_movements`: append-only. Entrada (+), consumo por procedimento (−, com paciente
  e item do plano: rastreabilidade de implantes e materiais), saída manual (−: perda,
  vencido, uso avulso) e ajuste de inventário (±). Baixa automática: ao realizar um item
  do plano, os materiais da ficha técnica saem pelo lote que vence primeiro (FEFO).

Gatilhos da migração 0015: saldo do lote nunca negativo; sinal coerente com o tipo;
lote não muda material nem custo.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class MovementKind(StrEnum):
    ENTRADA = "entrada"
    CONSUMO = "consumo"
    SAIDA = "saida"
    AJUSTE = "ajuste"


class Material(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_materials_id_clinic"),
        UniqueConstraint("clinic_id", "name", name="uq_materials_clinic_name"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(150))
    unit: Mapped[str] = mapped_column(String(20))  # ex.: un, ml, g, cx, par, tubo
    category: Mapped[str | None] = mapped_column(String(100))
    # 4 casas: materiais são comprados em caixa e usados em frações (ex.: R$ 0,0350 por ml).
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    # Alerta de reposição quando o saldo total fica abaixo disto (opcional).
    min_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class StockLot(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "stock_lots"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_stock_lots_id_clinic"),
        UniqueConstraint("id", "material_id", "clinic_id", name="uq_stock_lots_id_material"),
        ForeignKeyConstraint(
            ["material_id", "clinic_id"],
            ["materials.id", "materials.clinic_id"],
            name="fk_stock_lots_material_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_stock_lots_material", "material_id", "expires_on"),
        Index("ix_stock_lots_expires", "clinic_id", "expires_on"),
    )

    material_id: Mapped[uuid.UUID] = mapped_column()
    lot_code: Mapped[str | None] = mapped_column(String(60))
    expires_on: Mapped[date | None] = mapped_column(Date)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    received_on: Mapped[date] = mapped_column(Date)
    supplier: Mapped[str | None] = mapped_column(String(150))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class StockMovement(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["lot_id", "material_id", "clinic_id"],
            ["stock_lots.id", "stock_lots.material_id", "stock_lots.clinic_id"],
            name="fk_stock_movements_lot_same_material",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_stock_movements_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_item_id", "clinic_id"],
            ["treatment_plan_items.id", "treatment_plan_items.clinic_id"],
            name="fk_stock_movements_plan_item_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_stock_movements_lot", "lot_id", "created_at"),
        Index("ix_stock_movements_material", "material_id", "created_at"),
        Index("ix_stock_movements_patient", "patient_id"),
    )

    lot_id: Mapped[uuid.UUID] = mapped_column()
    material_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[MovementKind] = mapped_column(
        Enum(
            MovementKind,
            native_enum=False,
            length=20,
            values_callable=lambda x: [m.value for m in x],
            validate_strings=True,
            create_constraint=False,  # o CHECK é criado na migração
        )
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4))  # negativo nas saídas
    reason: Mapped[str | None] = mapped_column(String(300))
    patient_id: Mapped[uuid.UUID | None] = mapped_column()
    plan_item_id: Mapped[uuid.UUID | None] = mapped_column()
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
