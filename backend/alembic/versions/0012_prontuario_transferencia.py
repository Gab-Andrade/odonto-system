"""prontuario: transferência de atendimento aberto para outro dentista

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"

_GUARD_HEAD = """
        CREATE OR REPLACE FUNCTION encounter_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'aberto' THEN
                    RAISE EXCEPTION 'atendimento nasce aberto'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.status = 'fechado' THEN
                RAISE EXCEPTION 'atendimento fechado não pode ser alterado'
                    USING ERRCODE = 'check_violation';
            END IF;
"""
_GUARD_TAIL = """
            IF NEW.status = 'fechado' AND NEW.closed_by IS DISTINCT FROM NEW.dentist_id THEN
                RAISE EXCEPTION 'só o dentista do atendimento o fecha'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
"""

# Nova regra: o dentista muda só com o registro da transferência na mesma transação.
GUARD_WITH_TRANSFER = (
    _GUARD_HEAD
    + """
            IF NEW.patient_id <> OLD.patient_id OR NEW.clinic_id <> OLD.clinic_id
                    OR NEW.started_at <> OLD.started_at
                    OR NEW.appointment_id IS DISTINCT FROM OLD.appointment_id THEN
                RAISE EXCEPTION 'paciente, início e agendamento do atendimento não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.dentist_id <> OLD.dentist_id AND NOT EXISTS (
                SELECT 1 FROM encounter_transfers t
                WHERE t.encounter_id = OLD.id AND t.from_dentist_id = OLD.dentist_id
                    AND t.to_dentist_id = NEW.dentist_id AND t.created_at = now()
            ) THEN
                RAISE EXCEPTION 'dentista do atendimento só muda por transferência registrada'
                    USING ERRCODE = 'check_violation';
            END IF;
"""
    + _GUARD_TAIL
)

# Versão da 0010 (dentista imutável), para o downgrade.
GUARD_ORIGINAL = (
    _GUARD_HEAD
    + """
            IF NEW.patient_id <> OLD.patient_id OR NEW.dentist_id <> OLD.dentist_id
                    OR NEW.clinic_id <> OLD.clinic_id OR NEW.started_at <> OLD.started_at
                    OR NEW.appointment_id IS DISTINCT FROM OLD.appointment_id THEN
                RAISE EXCEPTION 'paciente, dentista, início e agendamento do atendimento não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
"""
    + _GUARD_TAIL
)


def upgrade() -> None:
    op.create_table(
        "encounter_transfers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.Uuid(),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_dentist_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "to_dentist_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("transferred_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id", "clinic_id"],
            ["encounters.id", "encounters.clinic_id"],
            name="fk_encounter_transfers_encounter_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("from_dentist_id <> to_dentist_id", name="different_dentists"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
    )
    op.create_index("ix_encounter_transfers_clinic_id", "encounter_transfers", ["clinic_id"])
    op.create_index(
        "ix_encounter_transfers_encounter", "encounter_transfers", ["encounter_id", "created_at"]
    )
    for stmt in enable_tenant_rls("encounter_transfers"):
        op.execute(stmt)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON encounter_transfers FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )
    op.execute(GUARD_WITH_TRANSFER)


def downgrade() -> None:
    op.execute(GUARD_ORIGINAL)
    for stmt in disable_tenant_rls("encounter_transfers"):
        op.execute(stmt)
    op.drop_table("encounter_transfers")
