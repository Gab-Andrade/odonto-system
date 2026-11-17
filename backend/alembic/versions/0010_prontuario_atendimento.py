"""prontuario: atendimentos, evolução clínica imutável com adendos e assinaturas

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
ENCOUNTER_STATUSES = ("aberto", "fechado")
NOTE_KINDS = ("evolucao", "adendo")
SIGNATURE_METHODS = ("simples", "icp_brasil")
TENANT_TABLES = ("encounters", "clinical_notes", "clinical_note_signatures")


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _created_at(name: str = "created_at") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _revoke(privileges: str, table: str) -> str:
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE {privileges} ON {table} FROM {APP_ROLE};
            END IF;
        END $$;
    """


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column(
            "dentist_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("appointment_id", sa.Uuid()),
        sa.Column("status", sa.String(20), server_default="aberto", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        _created_at(),
        _created_at("updated_at"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_encounters_id_clinic"),
        sa.UniqueConstraint("id", "patient_id", "clinic_id", name="uq_encounters_id_patient"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_encounters_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_encounters_appointment_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", ENCOUNTER_STATUSES), name="status_valid"),
        sa.CheckConstraint(
            "(status = 'fechado') = (closed_at IS NOT NULL)", name="closed_at_when_closed"
        ),
    )
    op.create_index("ix_encounters_clinic_id", "encounters", ["clinic_id"])
    op.create_index("ix_encounters_patient", "encounters", ["patient_id", "started_at"])
    # Um atendimento por agendamento.
    op.create_index(
        "uq_encounters_appointment",
        "encounters",
        ["appointment_id"],
        unique=True,
        postgresql_where=sa.text("appointment_id IS NOT NULL"),
    )

    op.create_table(
        "clinical_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amends_id", sa.Uuid()),
        sa.Column(
            "author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_clinical_notes_id_clinic"),
        sa.UniqueConstraint(
            "id", "encounter_id", "clinic_id", name="uq_clinical_notes_id_encounter"
        ),
        # O paciente da evolução é o do atendimento.
        sa.ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_clinical_notes_encounter_same_patient",
            ondelete="RESTRICT",
        ),
        # O adendo fica no mesmo atendimento da evolução corrigida.
        sa.ForeignKeyConstraint(
            ["amends_id", "encounter_id", "clinic_id"],
            ["clinical_notes.id", "clinical_notes.encounter_id", "clinical_notes.clinic_id"],
            name="fk_clinical_notes_amends_same_encounter",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("kind", NOTE_KINDS), name="kind_valid"),
        sa.CheckConstraint("(kind = 'adendo') = (amends_id IS NOT NULL)", name="adendo_has_target"),
        sa.CheckConstraint("length(btrim(content)) > 0", name="content_not_blank"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_sha256"),
    )
    op.create_index("ix_clinical_notes_clinic_id", "clinical_notes", ["clinic_id"])
    op.create_index("ix_clinical_notes_patient", "clinical_notes", ["patient_id", "performed_at"])
    op.create_index("ix_clinical_notes_encounter", "clinical_notes", ["encounter_id", "created_at"])

    op.create_table(
        "clinical_note_signatures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column(
            "signer_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text()),
        sa.Column("certificate", sa.Text()),
        _created_at("signed_at"),
        sa.ForeignKeyConstraint(
            ["note_id", "clinic_id"],
            ["clinical_notes.id", "clinical_notes.clinic_id"],
            name="fk_clinical_note_signatures_note_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("method", SIGNATURE_METHODS), name="method_valid"),
        sa.CheckConstraint(
            "method = 'simples' OR (signature IS NOT NULL AND certificate IS NOT NULL)",
            name="icp_has_signature",
        ),
    )
    op.create_index(
        "ix_clinical_note_signatures_clinic_id", "clinical_note_signatures", ["clinic_id"]
    )
    op.create_index("ix_clinical_note_signatures_note", "clinical_note_signatures", ["note_id"])

    # Atendimento: nasce aberto; só o dentista dele fecha; fechado não muda; paciente,
    # dentista e origem nunca mudam.
    op.execute(
        """
        CREATE FUNCTION encounter_guard() RETURNS trigger
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
            IF NEW.patient_id <> OLD.patient_id OR NEW.dentist_id <> OLD.dentist_id
                    OR NEW.clinic_id <> OLD.clinic_id OR NEW.started_at <> OLD.started_at
                    OR NEW.appointment_id IS DISTINCT FROM OLD.appointment_id THEN
                RAISE EXCEPTION 'paciente, dentista, início e agendamento do atendimento não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.status = 'fechado' AND NEW.closed_by IS DISTINCT FROM OLD.dentist_id THEN
                RAISE EXCEPTION 'só o dentista do atendimento o fecha'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_encounter_guard BEFORE INSERT OR UPDATE ON encounters "
        "FOR EACH ROW EXECUTE FUNCTION encounter_guard()"
    )

    # Evolução: só em atendimento aberto e pelo dentista dele. Adendo: só sobre evolução e
    # pelo autor dela. FOR SHARE espera um fechamento concorrente terminar.
    op.execute(
        """
        CREATE FUNCTION clinical_note_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            enc_status text;
            enc_dentist uuid;
            target_kind text;
            target_author uuid;
        BEGIN
            IF NEW.kind = 'evolucao' THEN
                SELECT status, dentist_id INTO enc_status, enc_dentist
                    FROM encounters WHERE id = NEW.encounter_id FOR SHARE;
                IF enc_status IS DISTINCT FROM 'aberto' THEN
                    RAISE EXCEPTION 'evolução só em atendimento aberto'
                        USING ERRCODE = 'check_violation';
                END IF;
                IF NEW.author_id <> enc_dentist THEN
                    RAISE EXCEPTION 'evolução só pelo dentista do atendimento'
                        USING ERRCODE = 'check_violation';
                END IF;
            ELSE
                SELECT kind, author_id INTO target_kind, target_author
                    FROM clinical_notes WHERE id = NEW.amends_id;
                IF target_kind IS DISTINCT FROM 'evolucao'
                        OR target_author IS DISTINCT FROM NEW.author_id THEN
                    RAISE EXCEPTION 'adendo só sobre evolução e pelo autor dela'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_clinical_note_guard BEFORE INSERT ON clinical_notes "
        "FOR EACH ROW EXECUTE FUNCTION clinical_note_guard()"
    )

    # Assinatura cobre exatamente o conteúdo gravado; a simples é sempre do próprio autor.
    op.execute(
        """
        CREATE FUNCTION clinical_note_signature_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            note_hash text;
            note_author uuid;
        BEGIN
            SELECT content_hash, author_id INTO note_hash, note_author
                FROM clinical_notes WHERE id = NEW.note_id;
            IF NEW.content_hash IS DISTINCT FROM note_hash THEN
                RAISE EXCEPTION 'assinatura não confere com o conteúdo da evolução'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.method = 'simples' AND NEW.signer_id IS DISTINCT FROM note_author THEN
                RAISE EXCEPTION 'assinatura simples só pelo autor da evolução'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_clinical_note_signature_guard BEFORE INSERT "
        "ON clinical_note_signatures "
        "FOR EACH ROW EXECUTE FUNCTION clinical_note_signature_guard()"
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Registro clínico (guarda mínima de 20 anos): nada se apaga; evolução e assinatura
    # também não se alteram.
    op.execute(_revoke("DELETE, TRUNCATE", "encounters"))
    op.execute(_revoke("UPDATE, DELETE, TRUNCATE", "clinical_notes"))
    op.execute(_revoke("UPDATE, DELETE, TRUNCATE", "clinical_note_signatures"))


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.execute("DROP TRIGGER trg_clinical_note_signature_guard ON clinical_note_signatures")
    op.execute("DROP FUNCTION clinical_note_signature_guard()")
    op.drop_table("clinical_note_signatures")
    op.execute("DROP TRIGGER trg_clinical_note_guard ON clinical_notes")
    op.execute("DROP FUNCTION clinical_note_guard()")
    op.drop_table("clinical_notes")
    op.execute("DROP TRIGGER trg_encounter_guard ON encounters")
    op.execute("DROP FUNCTION encounter_guard()")
    op.drop_table("encounters")
