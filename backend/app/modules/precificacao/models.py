"""Precificação: tabelas de preço versionadas, herança, atribuição e resolução.

- PriceTable: tabela de preço da clínica. Pode herdar de uma tabela-pai (fixada na criação).
- PriceTableVersion: versão da tabela. O rascunho é editável; a versão publicada é imutável
  e vale a partir de `valid_from`. O ajuste percentual sobre a tabela-pai fica na versão,
  para que mudar o ajuste também gere histórico.
- PriceItem: preço de um procedimento numa versão. Numa tabela filha, o item é um override
  do preço herdado.
- PriceAssignment: liga uma tabela a um escopo (clínica, dentista, convênio) com prioridade.
  Na resolução, vence a menor prioridade entre as atribuições que se aplicam.
- PriceSnapshot: resolução congelada (preço + memória de cálculo). Append-only. É o que um
  orçamento guarda, para que mudanças futuras na tabela não alterem o que já foi emitido.

Integridade entre clínicas: as referências internas usam FK composta (id, clinic_id), porque
a checagem de FK do PostgreSQL não passa pelo RLS.

Imutabilidade: a de versões publicadas e seus itens é garantida no service (não no banco).
Isso basta porque o snapshot copia os valores; a de snapshots é garantida no banco (REVOKE).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class TableStatus(StrEnum):
    ATIVA = "ativa"
    ARQUIVADA = "arquivada"


class VersionStatus(StrEnum):
    RASCUNHO = "rascunho"
    PUBLICADA = "publicada"


class ScopeType(StrEnum):
    CLINICA = "clinica"
    DENTISTA = "dentista"
    CONVENIO = "convenio"


def _enum(enum_cls: type[StrEnum], length: int = 20) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class PriceTable(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_tables"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_price_tables_id_clinic"),
        UniqueConstraint("clinic_id", "name", name="uq_price_tables_clinic_name"),
        ForeignKeyConstraint(
            ["parent_table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_tables_parent_same_clinic",
            ondelete="RESTRICT",
        ),
    )

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500))
    parent_table_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[TableStatus] = mapped_column(
        _enum(TableStatus), default=TableStatus.ATIVA, server_default=TableStatus.ATIVA.value
    )


class PriceTableVersion(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_table_versions"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_price_table_versions_id_clinic"),
        UniqueConstraint("table_id", "version", name="uq_price_table_versions_table_version"),
        ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_table_versions_table_same_clinic",
            ondelete="CASCADE",
        ),
        # No máximo um rascunho por tabela.
        Index(
            "uq_price_table_versions_one_draft",
            "table_id",
            unique=True,
            postgresql_where=text("status = 'rascunho'"),
        ),
    )

    table_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(
        _enum(VersionStatus),
        default=VersionStatus.RASCUNHO,
        server_default=VersionStatus.RASCUNHO.value,
    )
    adjustment_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    valid_from: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class PriceItem(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_items"
    __table_args__ = (
        UniqueConstraint("version_id", "procedure_code", name="uq_price_items_version_code"),
        ForeignKeyConstraint(
            ["version_id", "clinic_id"],
            ["price_table_versions.id", "price_table_versions.clinic_id"],
            name="fk_price_items_version_same_clinic",
            ondelete="CASCADE",
        ),
        CheckConstraint("price >= 0", name="price_non_negative"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column()
    procedure_code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class PriceAssignment(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_assignments"
    __table_args__ = (
        UniqueConstraint(
            "table_id",
            "scope_type",
            "scope_id",
            name="uq_price_assignments_table_scope",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_assignments_table_same_clinic",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(scope_type = 'clinica' AND scope_id IS NULL) OR "
            "(scope_type <> 'clinica' AND scope_id IS NOT NULL)",
            name="scope_id_consistent",
        ),
        CheckConstraint("priority >= 0", name="priority_non_negative"),
    )

    table_id: Mapped[uuid.UUID] = mapped_column()
    scope_type: Mapped[ScopeType] = mapped_column(_enum(ScopeType))
    # Usuário (dentista) ou convênio. Sem FK: o alvo depende do tipo de escopo.
    scope_id: Mapped[uuid.UUID | None] = mapped_column()
    priority: Mapped[int] = mapped_column(Integer)


class PriceSnapshot(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_snapshots_table_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["version_id", "clinic_id"],
            ["price_table_versions.id", "price_table_versions.clinic_id"],
            name="fk_price_snapshots_version_same_clinic",
            ondelete="RESTRICT",
        ),
    )

    procedure_code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    table_id: Mapped[uuid.UUID] = mapped_column()
    version_id: Mapped[uuid.UUID] = mapped_column()
    dentist_id: Mapped[uuid.UUID | None] = mapped_column()
    insurer_id: Mapped[uuid.UUID | None] = mapped_column()
    effective_on: Mapped[date] = mapped_column(Date)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
