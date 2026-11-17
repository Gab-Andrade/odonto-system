"""odontograma: composição da arcada do paciente (append-only)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
TABLE = "dental_arch_configs"
DENTITIONS = ("permanente", "decidua", "mista")
# FDI: permanentes 11–48 (posição 1–8), decíduos 51–85 (posição 1–5).
VALID_TEETH = [q * 10 + p for q in (1, 2, 3, 4) for p in range(1, 9)] + [
    q * 10 + p for q in (5, 6, 7, 8) for p in range(1, 6)
]


def upgrade() -> None:
    teeth_array = "ARRAY[" + ", ".join(str(t) for t in VALID_TEETH) + "]::smallint[]"
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
        sa.Column("dentition", sa.String(20), nullable=False),
        sa.Column("teeth", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("notes", sa.String(500)),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        # clock_timestamp(): a mais recente é a vigente, e a ordem tem de ser a real.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_dental_arch_configs_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "dentition IN (" + ", ".join(f"'{d}'" for d in DENTITIONS) + ")",
            name="dentition_valid",
        ),
        # Repetição e vaga ocupada por dois dentes ficam no service (CHECK não tem
        # subconsulta); aqui só numeração FDI e tamanho.
        sa.CheckConstraint(
            f"cardinality(teeth) BETWEEN 1 AND 52 AND array_ndims(teeth) = 1 "
            f"AND teeth <@ {teeth_array}",
            name="teeth_fdi",
        ),
    )
    op.create_index(f"ix_{TABLE}_clinic_id", TABLE, ["clinic_id"])
    op.create_index(f"ix_{TABLE}_patient", TABLE, ["patient_id", "created_at"])

    for stmt in enable_tenant_rls(TABLE):
        op.execute(stmt)

    # Histórico clínico: append-only (uma mudança de dentição é um registro novo).
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
    op.drop_table(TABLE)
