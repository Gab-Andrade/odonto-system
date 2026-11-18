"""painel: metas mensais da clínica e por dentista

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "panel_goals"
METRICS = ("recebido", "producao", "procedimentos", "aprovado")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.Uuid(),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(20), nullable=False),
        sa.Column("dentist_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("target", sa.Numeric(14, 2), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "clinic_id",
            "month",
            "metric",
            "dentist_id",
            name="uq_panel_goals_month_metric_dentist",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "metric IN (" + ", ".join(f"'{m}'" for m in METRICS) + ")", name="metric_valid"
        ),
        sa.CheckConstraint("extract(day from month) = 1", name="month_first_day"),
        sa.CheckConstraint("target > 0", name="target_positive"),
        # Recebimento não é atribuído a dentista: meta de recebido é só da clínica.
        sa.CheckConstraint(
            "metric <> 'recebido' OR dentist_id IS NULL", name="recebido_clinic_only"
        ),
    )
    op.create_index(f"ix_{TABLE}_clinic_id", TABLE, ["clinic_id"])
    for stmt in enable_tenant_rls(TABLE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in disable_tenant_rls(TABLE):
        op.execute(stmt)
    op.drop_table(TABLE)
