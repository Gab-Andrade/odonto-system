"""odontograma: cor pessoal de item da legenda (vale só para quem escolheu)

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tooth_status_user_colors"


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
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status_id", sa.Uuid(), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # Item da legenda da mesma clínica; some junto se o item for apagado.
        sa.ForeignKeyConstraint(
            ["status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_tooth_status_user_colors_status_same_clinic",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "clinic_id", "user_id", "status_id", name="uq_tooth_status_user_colors_user_status"
        ),
        sa.CheckConstraint("color ~ '^#[0-9A-F]{6}$'", name="color_valid"),
    )
    op.create_index(f"ix_{TABLE}_clinic_id", TABLE, ["clinic_id"])
    for stmt in enable_tenant_rls(TABLE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in disable_tenant_rls(TABLE):
        op.execute(stmt)
    op.drop_index(f"ix_{TABLE}_clinic_id", table_name=TABLE)
    op.drop_table(TABLE)
