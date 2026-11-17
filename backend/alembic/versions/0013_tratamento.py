"""tratamento: plano de tratamento e orçamento com preço congelado

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
PLAN_STATUSES = ("rascunho", "emitido", "aprovado", "recusado", "concluido", "cancelado")
ITEM_STATUSES = ("proposto", "aprovado", "recusado", "realizado", "cancelado")
TENANT_TABLES = ("treatment_settings", "treatment_plans", "treatment_plan_items")
VALID_TOOTH = (
    "tooth IS NULL OR (tooth / 10 BETWEEN 1 AND 4 AND tooth % 10 BETWEEN 1 AND 8) "
    "OR (tooth / 10 BETWEEN 5 AND 8 AND tooth % 10 BETWEEN 1 AND 5)"
)


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _user(name: str, ondelete: str = "SET NULL", nullable: bool = True) -> sa.Column:
    return sa.Column(
        name, sa.Uuid(), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable
    )


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # Alvo da FK composta dos itens (o snapshot de preço é da mesma clínica).
    op.create_unique_constraint(
        "uq_price_snapshots_id_clinic", "price_snapshots", ["id", "clinic_id"]
    )

    op.create_table(
        "treatment_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("validity_days", sa.Integer(), nullable=False),
        sa.Column("max_discount_pct", sa.Numeric(5, 2), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("clinic_id", name="uq_treatment_settings_clinic"),
        sa.CheckConstraint("validity_days BETWEEN 1 AND 365", name="validity_range"),
        sa.CheckConstraint("max_discount_pct BETWEEN 0 AND 100", name="discount_range"),
    )
    op.create_index("ix_treatment_settings_clinic_id", "treatment_settings", ["clinic_id"])

    op.create_table(
        "treatment_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        _user("dentist_id", "RESTRICT", nullable=False),
        sa.Column("status", sa.String(20), server_default="rascunho", nullable=False),
        sa.Column("title", sa.String(120)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("discount_pct", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        _user("issued_by"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        _user("decided_by"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.String(300)),
        _user("created_by"),
        *_timestamps(),
        sa.UniqueConstraint("id", "clinic_id", name="uq_treatment_plans_id_clinic"),
        sa.UniqueConstraint("id", "patient_id", "clinic_id", name="uq_treatment_plans_id_patient"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_treatment_plans_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", PLAN_STATUSES), name="status_valid"),
        sa.CheckConstraint("discount_pct BETWEEN 0 AND 100", name="discount_range"),
        # Rascunho nunca foi emitido; emitido em diante sempre foi. Cancelado pode ser
        # um rascunho (sem emissão) ou um orçamento emitido.
        sa.CheckConstraint("status <> 'rascunho' OR issued_at IS NULL", name="draft_not_issued"),
        sa.CheckConstraint(
            "status IN ('rascunho', 'cancelado') OR issued_at IS NOT NULL",
            name="issued_when_not_draft",
        ),
    )
    op.create_index("ix_treatment_plans_clinic_id", "treatment_plans", ["clinic_id"])
    op.create_index("ix_treatment_plans_patient", "treatment_plans", ["patient_id", "created_at"])
    op.create_index("ix_treatment_plans_status", "treatment_plans", ["clinic_id", "status"])

    op.create_table(
        "treatment_plan_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("procedure_code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(300)),
        sa.Column("tooth", sa.SmallInteger()),
        sa.Column("faces", sa.String(5)),
        sa.Column("notes", sa.String(500)),
        sa.Column("planned_status_id", sa.Uuid()),
        sa.Column("done_status_id", sa.Uuid()),
        sa.Column("status", sa.String(20), server_default="proposto", nullable=False),
        sa.Column("price_snapshot_id", sa.Uuid()),
        sa.Column("unit_price", sa.Numeric(12, 2)),
        sa.Column("encounter_id", sa.Uuid()),
        _user("performed_by", "RESTRICT"),
        sa.Column("performed_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.String(300)),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["plan_id", "patient_id", "clinic_id"],
            ["treatment_plans.id", "treatment_plans.patient_id", "treatment_plans.clinic_id"],
            name="fk_treatment_plan_items_plan_same_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["price_snapshot_id", "clinic_id"],
            ["price_snapshots.id", "price_snapshots.clinic_id"],
            name="fk_treatment_plan_items_snapshot_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["planned_status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_treatment_plan_items_planned_status_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["done_status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_treatment_plan_items_done_status_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_treatment_plan_items_encounter_same_patient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", ITEM_STATUSES), name="status_valid"),
        sa.CheckConstraint(VALID_TOOTH, name="tooth_fdi"),
        sa.CheckConstraint(
            "faces IS NULL OR (tooth IS NOT NULL AND faces ~ '^M?D?O?V?L?$' AND faces <> '')",
            name="faces_valid",
        ),
        sa.CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="price_not_negative"),
        sa.CheckConstraint(
            "(unit_price IS NULL) = (price_snapshot_id IS NULL)", name="price_with_snapshot"
        ),
        sa.CheckConstraint(
            "status <> 'realizado' OR (encounter_id IS NOT NULL AND performed_by IS NOT NULL "
            "AND performed_at IS NOT NULL)",
            name="performed_has_encounter",
        ),
    )
    op.create_index("ix_treatment_plan_items_clinic_id", "treatment_plan_items", ["clinic_id"])
    op.create_index(
        "ix_treatment_plan_items_plan", "treatment_plan_items", ["plan_id", "sort_order"]
    )
    op.create_index(
        "ix_treatment_plan_items_performed", "treatment_plan_items", ["clinic_id", "performed_at"]
    )

    # Preço congelado não muda; desconto e paciente fixos depois de emitido; item só
    # entra/sai no rascunho; status finais do item não mudam.
    op.execute(
        """
        CREATE FUNCTION treatment_plan_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.patient_id <> OLD.patient_id OR NEW.clinic_id <> OLD.clinic_id THEN
                RAISE EXCEPTION 'paciente do plano não muda'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status <> 'rascunho' AND (
                NEW.discount_pct <> OLD.discount_pct OR NEW.dentist_id <> OLD.dentist_id
                OR NEW.status = 'rascunho'
            ) THEN
                RAISE EXCEPTION 'orçamento emitido não muda desconto nem responsável'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_treatment_plan_guard BEFORE UPDATE ON treatment_plans "
        "FOR EACH ROW EXECUTE FUNCTION treatment_plan_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION treatment_plan_item_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            plan_status text;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                SELECT status INTO plan_status FROM treatment_plans WHERE id = NEW.plan_id;
                IF plan_status IS DISTINCT FROM 'rascunho' THEN
                    RAISE EXCEPTION 'item só é incluído com o plano em rascunho'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                SELECT status INTO plan_status FROM treatment_plans WHERE id = OLD.plan_id;
                IF plan_status IS DISTINCT FROM 'rascunho' THEN
                    RAISE EXCEPTION 'item de orçamento emitido não é apagado'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.price_snapshot_id IS NOT NULL AND (
                NEW.price_snapshot_id IS DISTINCT FROM OLD.price_snapshot_id
                OR NEW.unit_price IS DISTINCT FROM OLD.unit_price
                OR NEW.procedure_code <> OLD.procedure_code
                OR NEW.tooth IS DISTINCT FROM OLD.tooth
                OR NEW.faces IS DISTINCT FROM OLD.faces
                OR NEW.plan_id <> OLD.plan_id
            ) THEN
                RAISE EXCEPTION 'preço congelado do orçamento não muda'
                    USING ERRCODE = 'check_violation';
            END IF;
            -- Realizado, cancelado e recusado são finais.
            IF OLD.status IN ('realizado', 'cancelado', 'recusado') AND (
                NEW.status <> OLD.status
                OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
                OR NEW.performed_by IS DISTINCT FROM OLD.performed_by
                OR NEW.performed_at IS DISTINCT FROM OLD.performed_at
            ) THEN
                RAISE EXCEPTION 'item realizado, cancelado ou recusado não muda'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_treatment_plan_item_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON treatment_plan_items FOR EACH ROW EXECUTE FUNCTION treatment_plan_item_guard()"
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE DELETE, TRUNCATE ON treatment_plans FROM {APP_ROLE};
                REVOKE DELETE, TRUNCATE ON treatment_settings FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.execute("DROP TRIGGER trg_treatment_plan_item_guard ON treatment_plan_items")
    op.execute("DROP FUNCTION treatment_plan_item_guard()")
    op.drop_table("treatment_plan_items")
    op.execute("DROP TRIGGER trg_treatment_plan_guard ON treatment_plans")
    op.execute("DROP FUNCTION treatment_plan_guard()")
    op.drop_table("treatment_plans")
    op.drop_table("treatment_settings")
    op.drop_constraint("uq_price_snapshots_id_clinic", "price_snapshots", type_="unique")
