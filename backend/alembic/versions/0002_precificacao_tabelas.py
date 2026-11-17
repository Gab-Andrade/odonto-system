"""precificação: tabelas de preço versionadas, itens, atribuições e snapshots

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
TABLE_STATUS = ("ativa", "arquivada")
VERSION_STATUS = ("rascunho", "publicada")
SCOPE_TYPES = ("clinica", "dentista", "convenio")

TENANT_TABLES = (
    "price_tables",
    "price_table_versions",
    "price_items",
    "price_assignments",
    "price_snapshots",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "price_tables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("parent_table_id", sa.Uuid()),
        sa.Column("status", sa.String(20), server_default="ativa", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_price_tables_id_clinic"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_price_tables_clinic_name"),
        sa.ForeignKeyConstraint(
            ["parent_table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_tables_parent_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", TABLE_STATUS), name="status_valid"),
    )
    op.create_index("ix_price_tables_clinic_id", "price_tables", ["clinic_id"])

    op.create_table(
        "price_table_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="rascunho", nullable=False),
        sa.Column("adjustment_pct", sa.Numeric(7, 4)),
        sa.Column("valid_from", sa.Date()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("published_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_price_table_versions_id_clinic"),
        sa.UniqueConstraint(
            "clinic_id", "table_id", "version", name="uq_price_table_versions_table_version"
        ),
        sa.ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_table_versions_table_same_clinic",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in("status", VERSION_STATUS), name="status_valid"),
        sa.CheckConstraint(
            "status <> 'publicada' OR valid_from IS NOT NULL", name="published_has_valid_from"
        ),
    )
    op.create_index("ix_price_table_versions_clinic_id", "price_table_versions", ["clinic_id"])
    op.create_index(
        "uq_price_table_versions_one_draft",
        "price_table_versions",
        ["clinic_id", "table_id"],
        unique=True,
        postgresql_where=sa.text("status = 'rascunho'"),
    )

    op.create_table(
        "price_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("procedure_code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "clinic_id", "version_id", "procedure_code", name="uq_price_items_version_code"
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "clinic_id"],
            ["price_table_versions.id", "price_table_versions.clinic_id"],
            name="fk_price_items_version_same_clinic",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("price >= 0", name="price_non_negative"),
    )
    op.create_index("ix_price_items_clinic_id", "price_items", ["clinic_id"])

    op.create_table(
        "price_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.Uuid()),
        sa.Column("priority", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "clinic_id",
            "table_id",
            "scope_type",
            "scope_id",
            name="uq_price_assignments_table_scope",
            postgresql_nulls_not_distinct=True,
        ),
        sa.ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_assignments_table_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("scope_type", SCOPE_TYPES), name="scope_type_valid"),
        sa.CheckConstraint(
            "(scope_type = 'clinica' AND scope_id IS NULL) OR "
            "(scope_type <> 'clinica' AND scope_id IS NOT NULL)",
            name="scope_id_consistent",
        ),
        sa.CheckConstraint("priority >= 0", name="priority_non_negative"),
    )
    op.create_index("ix_price_assignments_clinic_id", "price_assignments", ["clinic_id"])

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("procedure_code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("dentist_id", sa.Uuid()),
        sa.Column("insurer_id", sa.Uuid()),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("trace", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_price_snapshots_table_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "clinic_id"],
            ["price_table_versions.id", "price_table_versions.clinic_id"],
            name="fk_price_snapshots_version_same_clinic",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_price_snapshots_clinic_id", "price_snapshots", ["clinic_id"])

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Snapshots são o preço congelado de orçamentos: append-only para a aplicação.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON price_snapshots FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("price_snapshots")
    op.drop_table("price_assignments")
    op.drop_table("price_items")
    op.drop_index("uq_price_table_versions_one_draft", table_name="price_table_versions")
    op.drop_table("price_table_versions")
    op.drop_table("price_tables")
