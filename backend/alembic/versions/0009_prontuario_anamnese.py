"""prontuario: modelos de anamnese versionados e respostas imutáveis

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
VERSION_STATUSES = ("rascunho", "publicada", "substituida")
TENANT_TABLES = ("anamnesis_templates", "anamnesis_template_versions", "anamnesis_responses")


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


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"))


def upgrade() -> None:
    op.create_table(
        "anamnesis_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _user_fk("created_by"),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_anamnesis_templates_id_clinic"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_anamnesis_templates_clinic_name"),
    )
    op.create_index("ix_anamnesis_templates_clinic_id", "anamnesis_templates", ["clinic_id"])

    op.create_table(
        "anamnesis_template_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="rascunho", nullable=False),
        sa.Column("questions", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        _user_fk("created_by"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        _user_fk("published_by"),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_anamnesis_template_versions_id_clinic"),
        sa.UniqueConstraint(
            "id", "template_id", "clinic_id", name="uq_anamnesis_template_versions_id_template"
        ),
        sa.UniqueConstraint(
            "template_id", "number", name="uq_anamnesis_template_versions_template_number"
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "clinic_id"],
            ["anamnesis_templates.id", "anamnesis_templates.clinic_id"],
            name="fk_anamnesis_template_versions_template_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", VERSION_STATUSES), name="status_valid"),
        sa.CheckConstraint("number >= 1", name="number_positive"),
        sa.CheckConstraint(
            "(status = 'rascunho') = (published_at IS NULL)", name="published_at_when_published"
        ),
        sa.CheckConstraint("jsonb_typeof(questions) = 'array'", name="questions_is_array"),
    )
    op.create_index(
        "ix_anamnesis_template_versions_clinic_id", "anamnesis_template_versions", ["clinic_id"]
    )
    # Um rascunho e uma publicada por modelo, no máximo.
    for name, value in (("one_draft", "rascunho"), ("one_published", "publicada")):
        op.create_index(
            f"uq_anamnesis_template_versions_{name}",
            "anamnesis_template_versions",
            ["template_id"],
            unique=True,
            postgresql_where=sa.text(f"status = '{value}'"),
        )

    # Defesa no banco: versão que saiu de rascunho não muda as perguntas (as respostas
    # dependem delas), não volta a rascunho e não é apagada; número, modelo e clínica
    # nunca mudam. Só o rascunho pode ser descartado.
    op.execute(
        """
        CREATE FUNCTION anamnesis_version_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'rascunho' THEN
                    RAISE EXCEPTION 'versão publicada de anamnese não pode ser apagada'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN OLD;
            END IF;
            IF NEW.number <> OLD.number OR NEW.template_id <> OLD.template_id
                    OR NEW.clinic_id <> OLD.clinic_id THEN
                RAISE EXCEPTION 'número, modelo e clínica da versão não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status <> 'rascunho' AND (
                NEW.questions IS DISTINCT FROM OLD.questions OR NEW.status = 'rascunho'
            ) THEN
                RAISE EXCEPTION 'versão publicada de anamnese não pode ser alterada'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_anamnesis_version_guard "
        "BEFORE UPDATE OR DELETE ON anamnesis_template_versions "
        "FOR EACH ROW EXECUTE FUNCTION anamnesis_version_guard()"
    )

    op.create_table(
        "anamnesis_responses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("answers", JSONB(), nullable=False),
        sa.Column("alerts", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        _user_fk("filled_by"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_anamnesis_responses_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "template_id", "clinic_id"],
            [
                "anamnesis_template_versions.id",
                "anamnesis_template_versions.template_id",
                "anamnesis_template_versions.clinic_id",
            ],
            name="fk_anamnesis_responses_version_same_template",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("jsonb_typeof(answers) = 'object'", name="answers_is_object"),
        sa.CheckConstraint("jsonb_typeof(alerts) = 'array'", name="alerts_is_array"),
    )
    op.create_index("ix_anamnesis_responses_clinic_id", "anamnesis_responses", ["clinic_id"])
    op.create_index(
        "ix_anamnesis_responses_patient",
        "anamnesis_responses",
        ["patient_id", "template_id", "created_at"],
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Anamnese respondida é registro clínico: append-only para a aplicação.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON anamnesis_responses FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("anamnesis_responses")
    op.execute("DROP TRIGGER trg_anamnesis_version_guard ON anamnesis_template_versions")
    op.execute("DROP FUNCTION anamnesis_version_guard()")
    op.drop_table("anamnesis_template_versions")
    op.drop_table("anamnesis_templates")
