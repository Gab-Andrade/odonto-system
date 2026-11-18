"""odontograma: anotações livres por dente (append-only)

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
TABLE = "tooth_notes"
# FDI: permanentes 11–48 (posição 1–8), decíduos 51–85 (posição 1–5).
VALID_TOOTH = (
    "(tooth / 10 BETWEEN 1 AND 4 AND tooth % 10 BETWEEN 1 AND 8) "
    "OR (tooth / 10 BETWEEN 5 AND 8 AND tooth % 10 BETWEEN 1 AND 5)"
)


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
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("tooth", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_tooth_notes_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(VALID_TOOTH, name="tooth_fdi"),
        sa.CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
    )
    op.create_index(f"ix_{TABLE}_clinic_id", TABLE, ["clinic_id"])
    op.create_index(f"ix_{TABLE}_patient", TABLE, ["patient_id", "created_at"])
    for stmt in enable_tenant_rls(TABLE):
        op.execute(stmt)
    # Prontuário: a anotação não é alterada nem apagada; corrige-se com uma nova.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON {TABLE} FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for stmt in disable_tenant_rls(TABLE):
        op.execute(stmt)
    op.drop_index(f"ix_{TABLE}_patient", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_clinic_id", table_name=TABLE)
    op.drop_table(TABLE)
