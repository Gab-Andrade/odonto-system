"""imagens: exames de raio-X (DICOM) anexados ao paciente, arquivo e metadados imutáveis

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
TABLE = "imaging_exams"
KINDS = ("periapical", "interproximal", "panoramica", "tomografia", "outro")
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
        sa.Column("encounter_id", sa.Uuid()),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("teeth", postgresql.ARRAY(sa.SmallInteger())),
        sa.Column("exam_date", sa.Date()),
        sa.Column("notes", sa.String(1000)),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("modality", sa.String(16)),
        sa.Column("study_uid", sa.String(64)),
        sa.Column("series_uid", sa.String(64)),
        sa.Column("sop_uid", sa.String(64)),
        sa.Column("study_date", sa.Date()),
        sa.Column("study_description", sa.String(200)),
        sa.Column("series_description", sa.String(200)),
        sa.Column("body_part", sa.String(64)),
        sa.Column("manufacturer", sa.String(200)),
        sa.Column("rows", sa.Integer()),
        sa.Column("columns", sa.Integer()),
        sa.Column("dicom_patient_name", sa.String(200)),
        sa.Column("dicom_metadata", postgresql.JSONB(), nullable=False),
        # RESTRICT: o gatilho de imutabilidade barraria o SET NULL.
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("invalidation_reason", sa.String(300)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_imaging_exams_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            # Inclui o paciente: o atendimento tem de ser do mesmo paciente do exame.
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_imaging_exams_encounter_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("clinic_id", "patient_id", "sha256", name="uq_imaging_exams_file"),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")", name="kind_valid"
        ),
        sa.CheckConstraint(
            f"teeth IS NULL OR (cardinality(teeth) BETWEEN 1 AND 52 AND array_ndims(teeth) = 1 "
            f"AND teeth <@ {teeth_array})",
            name="teeth_fdi",
        ),
        sa.CheckConstraint("size_bytes > 0", name="size_positive"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        sa.CheckConstraint("jsonb_typeof(dicom_metadata) = 'object'", name="dicom_metadata_object"),
        sa.CheckConstraint(
            "(invalidated_at IS NULL) = (invalidation_reason IS NULL)", name="invalidation_reason"
        ),
    )
    op.create_index(f"ix_{TABLE}_clinic_id", TABLE, ["clinic_id"])
    op.create_index("ix_imaging_exams_patient", TABLE, ["patient_id", "exam_date"])
    for stmt in enable_tenant_rls(TABLE):
        op.execute(stmt)

    # O arquivo, o paciente e o que foi lido do DICOM não mudam; exame invalidado não muda
    # mais (nem volta a valer).
    op.execute(
        """
        CREATE FUNCTION imaging_exam_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.invalidated_at IS NOT NULL THEN
                RAISE EXCEPTION 'exame invalidado não pode ser alterado'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.clinic_id <> OLD.clinic_id OR NEW.patient_id <> OLD.patient_id
                    OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
                    OR NEW.file_name <> OLD.file_name OR NEW.size_bytes <> OLD.size_bytes
                    OR NEW.sha256 <> OLD.sha256 OR NEW.storage_key <> OLD.storage_key
                    OR NEW.modality IS DISTINCT FROM OLD.modality
                    OR NEW.study_uid IS DISTINCT FROM OLD.study_uid
                    OR NEW.series_uid IS DISTINCT FROM OLD.series_uid
                    OR NEW.sop_uid IS DISTINCT FROM OLD.sop_uid
                    OR NEW.study_date IS DISTINCT FROM OLD.study_date
                    OR NEW.dicom_patient_name IS DISTINCT FROM OLD.dicom_patient_name
                    OR NEW.dicom_metadata <> OLD.dicom_metadata
                    OR NEW.uploaded_by IS DISTINCT FROM OLD.uploaded_by
                    OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'arquivo, paciente e metadados do exame não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        f"CREATE TRIGGER trg_imaging_exam_guard BEFORE UPDATE ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION imaging_exam_guard()"
    )
    # Prontuário: sem exclusão pela aplicação.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE DELETE, TRUNCATE ON {TABLE} FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER trg_imaging_exam_guard ON {TABLE}")
    op.execute("DROP FUNCTION imaging_exam_guard()")
    for stmt in disable_tenant_rls(TABLE):
        op.execute(stmt)
    op.drop_table(TABLE)
