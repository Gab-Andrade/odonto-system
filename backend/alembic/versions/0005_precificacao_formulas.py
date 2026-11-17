"""precificação: tabelas calculadas por fórmula, fichas técnicas e variáveis

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_KINDS = ("fixa", "calculada")
TENANT_TABLES = ("cost_sheets", "cost_sheet_items", "pricing_variables")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # Tabelas existentes viram "fixa".
    op.add_column(
        "price_tables", sa.Column("kind", sa.String(20), server_default="fixa", nullable=False)
    )
    op.add_column("price_tables", sa.Column("calc_dentist_id", sa.Uuid()))
    op.create_check_constraint("kind_valid", "price_tables", _in("kind", TABLE_KINDS))
    op.create_check_constraint(
        "calc_dentist_only_calculated",
        "price_tables",
        "kind = 'calculada' OR calc_dentist_id IS NULL",
    )
    # Tabela calculada não herda de outra: os preços vêm da fórmula.
    op.create_check_constraint(
        "calculated_has_no_parent",
        "price_tables",
        "kind = 'fixa' OR parent_table_id IS NULL",
    )
    op.add_column("price_table_versions", sa.Column("formula", postgresql.JSONB()))
    op.add_column("price_table_versions", sa.Column("calculated_at", sa.DateTime(timezone=True)))
    op.add_column("price_table_versions", sa.Column("calc_inputs_hash", sa.String(64)))
    op.add_column("price_items", sa.Column("calc_trace", postgresql.JSONB()))

    op.create_table(
        "cost_sheets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("procedure_code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_cost_sheets_id_clinic"),
        sa.UniqueConstraint("clinic_id", "procedure_code", name="uq_cost_sheets_clinic_code"),
        sa.CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )
    op.create_index("ix_cost_sheets_clinic_id", "cost_sheets", ["clinic_id"])

    op.create_table(
        "cost_sheet_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("sheet_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "clinic_id", "sheet_id", "material_id", name="uq_cost_sheet_items_sheet_material"
        ),
        sa.ForeignKeyConstraint(
            ["sheet_id", "clinic_id"],
            ["cost_sheets.id", "cost_sheets.clinic_id"],
            name="fk_cost_sheet_items_sheet_same_clinic",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "clinic_id"],
            ["materials.id", "materials.clinic_id"],
            name="fk_cost_sheet_items_material_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    op.create_index("ix_cost_sheet_items_clinic_id", "cost_sheet_items", ["clinic_id"])

    op.create_table(
        "pricing_variables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(120)),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("dentist_id", sa.Uuid()),
        *_timestamps(),
        sa.UniqueConstraint(
            "clinic_id",
            "key",
            "dentist_id",
            name="uq_pricing_variables_key_dentist",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint("key ~ '^[a-z_][a-z0-9_]*$'", name="key_format"),
    )
    op.create_index("ix_pricing_variables_clinic_id", "pricing_variables", ["clinic_id"])

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("pricing_variables")
    op.drop_table("cost_sheet_items")
    op.drop_table("cost_sheets")
    op.drop_column("price_items", "calc_trace")
    op.drop_column("price_table_versions", "calc_inputs_hash")
    op.drop_column("price_table_versions", "calculated_at")
    op.drop_column("price_table_versions", "formula")
    op.drop_constraint("calculated_has_no_parent", "price_tables", type_="check")
    op.drop_constraint("calc_dentist_only_calculated", "price_tables", type_="check")
    op.drop_constraint("kind_valid", "price_tables", type_="check")
    op.drop_column("price_tables", "calc_dentist_id")
    op.drop_column("price_tables", "kind")
