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
- ImportJob / ImportProfile: importação de planilha (CSV/.xlsx) para o rascunho de uma
  tabela, e mapeamentos de colunas salvos. A lógica de leitura fica em importacao.py.

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


class TableKind(StrEnum):
    FIXA = "fixa"  # preços digitados ou importados
    CALCULADA = "calculada"  # preços gerados por fórmula a partir de custos


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
    kind: Mapped[TableKind] = mapped_column(
        _enum(TableKind), default=TableKind.FIXA, server_default=TableKind.FIXA.value
    )
    # Tabela calculada: de quem são as variáveis usadas (pró-labore, margem...). Vazio = clínica.
    calc_dentist_id: Mapped[uuid.UUID | None] = mapped_column()


class PriceTableVersion(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_table_versions"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_price_table_versions_id_clinic"),
        UniqueConstraint(
            "clinic_id", "table_id", "version", name="uq_price_table_versions_table_version"
        ),
        ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_table_versions_table_same_clinic",
            ondelete="CASCADE",
        ),
        # No máximo um rascunho por tabela.
        Index(
            "uq_price_table_versions_one_draft",
            "clinic_id",
            "table_id",
            unique=True,
            postgresql_where=text("status = 'rascunho'"),
        ),
        CheckConstraint(
            "calc_errors IS NULL OR calculated_at IS NOT NULL",
            name="calc_errors_only_when_calculated",
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
    # Tabela calculada: passos da fórmula ({"nome", "expressao"}) e quando os itens foram gerados.
    formula: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Hash dos insumos usados no cálculo (fórmula, variáveis, fichas, custos). Publicar
    # confere se continuam iguais, para não publicar preço calculado com custo antigo.
    calc_inputs_hash: Mapped[str | None] = mapped_column(String(64))
    # Procedimentos que falharam no último recálculo ({"procedimento", "erro"}). Ficam fora
    # dos itens; publicar com erros exige confirmação. Nulo enquanto não houve cálculo.
    # none_as_null: sem isso o SQLAlchemy grava None como JSON 'null' (não NULL) e o CHECK
    # calc_errors_only_when_calculated falha.
    calc_errors: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB(none_as_null=True))


class PriceItem(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_items"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "version_id", "procedure_code", name="uq_price_items_version_code"
        ),
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
    # Colunas extras da planilha que a clínica quis manter (ex.: "Tempo", "Observação").
    custom_fields: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    # Tabela calculada: memória de cálculo do item (entradas, materiais, passos).
    calc_trace: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PriceAssignment(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_assignments"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
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
        # Alvo da FK composta dos itens de orçamento (migração 0013).
        UniqueConstraint("id", "clinic_id", name="uq_price_snapshots_id_clinic"),
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


class ImportStatus(StrEnum):
    ANALISADA = "analisada"  # arquivo lido; aguardando mapeamento
    VALIDADA = "validada"  # mapeamento aplicado; relatório de erros e diferenças pronto
    APLICADA = "aplicada"  # itens gravados no rascunho da tabela


class ImportProfile(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    """Mapeamento de colunas salvo, para reaproveitar a cada nova versão da planilha."""

    __tablename__ = "import_profiles"
    __table_args__ = (UniqueConstraint("clinic_id", "name", name="uq_import_profiles_clinic_name"),)

    name: Mapped[str] = mapped_column(String(120))
    column_map: Mapped[dict[str, str | None]] = mapped_column(JSONB)
    extra_columns: Mapped[list[str]] = mapped_column(JSONB, default=list)


class ImportJob(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    """Uma importação de planilha para o rascunho de uma tabela.

    O arquivo não é guardado: as linhas lidas ficam em `rows`, com nome, tamanho e hash
    do arquivo para auditoria.
    """

    __tablename__ = "import_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_import_jobs_table_same_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["applied_version_id", "clinic_id"],
            ["price_table_versions.id", "price_table_versions.clinic_id"],
            name="fk_import_jobs_version_same_clinic",
            ondelete="RESTRICT",
        ),
    )

    table_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[ImportStatus] = mapped_column(
        _enum(ImportStatus),
        default=ImportStatus.ANALISADA,
        server_default=ImportStatus.ANALISADA.value,
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    file_sha256: Mapped[str] = mapped_column(String(64))
    detected: Mapped[dict[str, Any]] = mapped_column(JSONB)
    headers: Mapped[list[str]] = mapped_column(JSONB)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    column_map: Mapped[dict[str, str | None] | None] = mapped_column(JSONB)
    extra_columns: Mapped[list[str] | None] = mapped_column(JSONB)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    applied_version_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CostSheet(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    """Ficha técnica: o que um procedimento consome (tempo e materiais)."""

    __tablename__ = "cost_sheets"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_cost_sheets_id_clinic"),
        UniqueConstraint("clinic_id", "procedure_code", name="uq_cost_sheets_clinic_code"),
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )

    procedure_code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer)


class CostSheetItem(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "cost_sheet_items"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "sheet_id", "material_id", name="uq_cost_sheet_items_sheet_material"
        ),
        ForeignKeyConstraint(
            ["sheet_id", "clinic_id"],
            ["cost_sheets.id", "cost_sheets.clinic_id"],
            name="fk_cost_sheet_items_sheet_same_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["material_id", "clinic_id"],
            ["materials.id", "materials.clinic_id"],
            name="fk_cost_sheet_items_material_same_clinic",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    sheet_id: Mapped[uuid.UUID] = mapped_column()
    material_id: Mapped[uuid.UUID] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4))


class PricingVariable(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    """Variável de fórmula. Sem dentist_id: valor padrão da clínica; com: valor do dentista,
    que tem prioridade sobre o padrão nas tabelas calculadas daquele dentista."""

    __tablename__ = "pricing_variables"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "key",
            "dentist_id",
            name="uq_pricing_variables_key_dentist",
            postgresql_nulls_not_distinct=True,
        ),
    )

    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str | None] = mapped_column(String(120))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    dentist_id: Mapped[uuid.UUID | None] = mapped_column()
