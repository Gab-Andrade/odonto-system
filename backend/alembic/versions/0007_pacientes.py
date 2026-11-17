"""pacientes: cadastro com busca por nome (pg_trgm) e consentimentos LGPD append-only

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
SEXES = ("feminino", "masculino", "intersexo")
CONSENT_PURPOSES = ("tratamento_dados", "comunicacao", "uso_imagem")
CONSENT_GIVEN_BY = ("paciente", "responsavel")
TENANT_TABLES = ("patients", "patient_consents")


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
    # Busca por trecho do nome. Extensão "trusted": o dono do banco pode criá-la.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "patients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("social_name", sa.String(200)),
        sa.Column("search_name", sa.String(401), nullable=False),
        sa.Column("birth_date", sa.Date()),
        sa.Column("sex", sa.String(20)),
        sa.Column("cpf", sa.String(11)),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("phone_alt", sa.String(15)),
        sa.Column("email", sa.String(254)),
        sa.Column("zip_code", sa.String(8)),
        sa.Column("street", sa.String(200)),
        sa.Column("number", sa.String(20)),
        sa.Column("complement", sa.String(100)),
        sa.Column("district", sa.String(100)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(2)),
        sa.Column("guardian_name", sa.String(200)),
        sa.Column("guardian_cpf", sa.String(11)),
        sa.Column("guardian_phone", sa.String(15)),
        sa.Column("guardian_relationship", sa.String(50)),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_patients_id_clinic"),
        sa.CheckConstraint(f"sex IS NULL OR {_in('sex', SEXES)}", name="sex_valid"),
        sa.CheckConstraint("cpf ~ '^[0-9]{11}$'", name="cpf_digits"),
        sa.CheckConstraint("guardian_cpf ~ '^[0-9]{11}$'", name="guardian_cpf_digits"),
        sa.CheckConstraint("phone ~ '^[0-9]{8,15}$'", name="phone_digits"),
    )
    op.create_index("ix_patients_clinic_id", "patients", ["clinic_id"])
    # Unicidade com clinic_id (a checagem de unicidade ignora o RLS).
    op.create_index(
        "uq_patients_clinic_cpf",
        "patients",
        ["clinic_id", "cpf"],
        unique=True,
        postgresql_where=sa.text("cpf IS NOT NULL"),
    )
    op.create_index(
        "ix_patients_search_name_trgm",
        "patients",
        ["search_name"],
        postgresql_using="gin",
        postgresql_ops={"search_name": "gin_trgm_ops"},
    )

    op.create_table(
        "patient_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("given_by", sa.String(20), nullable=False),
        sa.Column("term_version", sa.String(40)),
        sa.Column("notes", sa.String(500)),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_patient_consents_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("purpose", CONSENT_PURPOSES), name="purpose_valid"),
        sa.CheckConstraint(_in("given_by", CONSENT_GIVEN_BY), name="given_by_valid"),
    )
    op.create_index("ix_patient_consents_clinic_id", "patient_consents", ["clinic_id"])
    op.create_index(
        "ix_patient_consents_patient", "patient_consents", ["patient_id", "purpose", "created_at"]
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Consentimento é prova: append-only para a aplicação (revogação é um novo evento).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON patient_consents FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("patient_consents")
    op.drop_table("patients")
    # pg_trgm fica: DROP EXTENSION pode afetar outros objetos e é inofensivo mantê-la.
