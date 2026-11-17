"""agenda: cadeiras, agendamentos e bloqueios sem conflito de horário, histórico append-only

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
KINDS = ("consulta", "bloqueio")
STATUSES = ("agendado", "confirmado", "atendido", "falta", "cancelado")
OCCUPYING = ("agendado", "confirmado", "atendido")
ACTIONS = ("criado", "reagendado", "alterado", "status")
TENANT_TABLES = ("chairs", "appointments", "appointment_events")


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
    # Igualdade de uuid dentro de índice GiST (constraint de exclusão). Extensão "trusted".
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "chairs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_chairs_id_clinic"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_chairs_clinic_name"),
    )
    op.create_index("ix_chairs_clinic_id", "chairs", ["clinic_id"])

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="agendado", nullable=False),
        sa.Column("patient_id", sa.Uuid()),
        sa.Column("dentist_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("chair_id", sa.Uuid()),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("procedure", sa.String(200)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("status_reason", sa.String(300)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_appointments_id_clinic"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_appointments_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chair_id", "clinic_id"],
            ["chairs.id", "chairs.clinic_id"],
            name="fk_appointments_chair_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("kind", KINDS), name="kind_valid"),
        sa.CheckConstraint(_in("status", STATUSES), name="status_valid"),
        sa.CheckConstraint("ends_at > starts_at", name="period_valid"),
        sa.CheckConstraint(
            "kind = 'bloqueio' OR (patient_id IS NOT NULL AND dentist_id IS NOT NULL)",
            name="consulta_has_patient_and_dentist",
        ),
        sa.CheckConstraint(
            "kind = 'consulta' OR (patient_id IS NULL "
            "AND (dentist_id IS NOT NULL OR chair_id IS NOT NULL))",
            name="bloqueio_has_target",
        ),
    )
    op.create_index("ix_appointments_clinic_id", "appointments", ["clinic_id"])
    op.create_index("ix_appointments_starts_at", "appointments", ["clinic_id", "starts_at"])
    op.create_index("ix_appointments_patient", "appointments", ["patient_id", "starts_at"])

    # Sem conflito de horário. clinic_id entra na constraint porque a checagem ignora o RLS.
    # '[)': terminar às 10h e começar às 10h não conflita. NULL em dentist_id/chair_id não
    # conflita com nada (bloqueio só de cadeira, consulta sem cadeira).
    occupying = _in("status", OCCUPYING)
    for column, name in (
        ("dentist_id", "excl_appointments_dentist_overlap"),
        ("chair_id", "excl_appointments_chair_overlap"),
    ):
        op.execute(
            f"ALTER TABLE appointments ADD CONSTRAINT {name} EXCLUDE USING gist "
            f"(clinic_id WITH =, {column} WITH =, "
            f"tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE ({occupying})"
        )

    op.create_table(
        "appointment_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_appointment_events_appointment_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("action", ACTIONS), name="action_valid"),
        sa.CheckConstraint(_in("status", STATUSES), name="status_valid"),
    )
    op.create_index("ix_appointment_events_clinic_id", "appointment_events", ["clinic_id"])
    op.create_index(
        "ix_appointment_events_appointment", "appointment_events", ["appointment_id", "created_at"]
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Histórico de status alimenta faltas e indicadores: append-only para a aplicação.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON appointment_events FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("appointment_events")
    op.drop_table("appointments")
    op.drop_table("chairs")
    # btree_gist fica, como o pg_trgm da 0007.
