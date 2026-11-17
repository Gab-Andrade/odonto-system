"""precificação: importação de planilhas (perfis, importações) e campos extras nos itens

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMPORT_STATUS = ("analisada", "validada", "aplicada")
TENANT_TABLES = ("import_profiles", "import_jobs")


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
    op.add_column("price_items", sa.Column("custom_fields", postgresql.JSONB()))

    op.create_table(
        "import_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("column_map", postgresql.JSONB(), nullable=False),
        sa.Column("extra_columns", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("clinic_id", "name", name="uq_import_profiles_clinic_name"),
    )
    op.create_index("ix_import_profiles_clinic_id", "import_profiles", ["clinic_id"])

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), server_default="analisada", nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("detected", postgresql.JSONB(), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=False),
        sa.Column("rows", postgresql.JSONB(), nullable=False),
        sa.Column("column_map", postgresql.JSONB()),
        sa.Column("extra_columns", postgresql.JSONB()),
        sa.Column("report", postgresql.JSONB()),
        sa.Column("applied_version_id", sa.Uuid()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["table_id", "clinic_id"],
            ["price_tables.id", "price_tables.clinic_id"],
            name="fk_import_jobs_table_same_clinic",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["applied_version_id", "clinic_id"],
            ["price_table_versions.id", "price_table_versions.clinic_id"],
            name="fk_import_jobs_version_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", IMPORT_STATUS), name="status_valid"),
        sa.CheckConstraint(
            "status <> 'aplicada' OR applied_version_id IS NOT NULL", name="applied_has_version"
        ),
    )
    op.create_index("ix_import_jobs_clinic_id", "import_jobs", ["clinic_id"])

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("import_jobs")
    op.drop_table("import_profiles")
    op.drop_column("price_items", "custom_fields")
