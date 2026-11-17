"""estoque: cadastro de materiais com custo unitário

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_materials_id_clinic"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_materials_clinic_name"),
        sa.CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )
    op.create_index("ix_materials_clinic_id", "materials", ["clinic_id"])
    for stmt in enable_tenant_rls("materials"):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in disable_tenant_rls("materials"):
        op.execute(stmt)
    op.drop_table("materials")
