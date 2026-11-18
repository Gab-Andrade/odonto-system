"""financeiro: configuração por clínica (dentista lê o extrato do paciente se liberado)

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "financial_settings"


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
        sa.Column("dentist_can_view", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("clinic_id", name="uq_financial_settings_clinic"),
    )
    op.create_index(f"ix_{TABLE}_clinic_id", TABLE, ["clinic_id"])
    for stmt in enable_tenant_rls(TABLE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in disable_tenant_rls(TABLE):
        op.execute(stmt)
    op.drop_table(TABLE)
