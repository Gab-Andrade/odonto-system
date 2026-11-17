"""odontograma: legenda por clínica e histórico de marcações (append-only)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
KINDS = ("patologia", "planejado", "realizado")
SCOPES = ("dente", "face")
ACTIONS = ("marcar", "remover")
FACES = ("M", "D", "O", "V", "L")
TENANT_TABLES = ("tooth_statuses", "odontogram_events")
# FDI: permanentes 11–48 (posição 1–8), decíduos 51–85 (posição 1–5).
VALID_TOOTH = (
    "(tooth / 10 BETWEEN 1 AND 4 AND tooth % 10 BETWEEN 1 AND 8) "
    "OR (tooth / 10 BETWEEN 5 AND 8 AND tooth % 10 BETWEEN 1 AND 5)"
)


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _now(name: str) -> sa.Column:
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
        "tooth_statuses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_tooth_statuses_id_clinic"),
        sa.UniqueConstraint("clinic_id", "code", name="uq_tooth_statuses_clinic_code"),
        sa.CheckConstraint(_in("kind", KINDS), name="kind_valid"),
        sa.CheckConstraint(_in("scope", SCOPES), name="scope_valid"),
        sa.CheckConstraint("color ~ '^#[0-9A-F]{6}$'", name="color_hex"),
        sa.CheckConstraint("code ~ '^[a-z0-9_]{1,40}$'", name="code_slug"),
    )
    op.create_index("ix_tooth_statuses_clinic_id", "tooth_statuses", ["clinic_id"])

    op.create_table(
        "odontogram_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("tooth", sa.SmallInteger(), nullable=False),
        sa.Column("face", sa.String(1)),
        sa.Column("status_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("encounter_id", sa.Uuid()),
        sa.Column("notes", sa.String(500)),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        # clock_timestamp(), não now(): a ordem dos eventos reconstrói o odontograma, e as
        # escritas são serializadas por paciente (lock); now() seria o início da transação,
        # anterior à espera pelo lock.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_odontogram_events_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_odontogram_events_status_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_odontogram_events_encounter_same_patient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(VALID_TOOTH, name="tooth_fdi"),
        sa.CheckConstraint(f"face IS NULL OR {_in('face', FACES)}", name="face_valid"),
        sa.CheckConstraint(_in("action", ACTIONS), name="action_valid"),
    )
    op.create_index("ix_odontogram_events_clinic_id", "odontogram_events", ["clinic_id"])
    op.create_index(
        "ix_odontogram_events_patient", "odontogram_events", ["patient_id", "created_at"]
    )

    # Evento: face coerente com o escopo do item; só item ativo é marcado. FOR SHARE
    # serializa com uma mudança de escopo concorrente do item.
    op.execute(
        """
        CREATE FUNCTION odontogram_event_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            st_scope text;
            st_active boolean;
        BEGIN
            SELECT scope, active INTO st_scope, st_active
                FROM tooth_statuses WHERE id = NEW.status_id FOR SHARE;
            IF (st_scope = 'face') <> (NEW.face IS NOT NULL) THEN
                RAISE EXCEPTION 'face incompatível com o escopo do item da legenda'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.action = 'marcar' AND st_active IS NOT TRUE THEN
                RAISE EXCEPTION 'item da legenda desativado'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_odontogram_event_guard BEFORE INSERT ON odontogram_events "
        "FOR EACH ROW EXECUTE FUNCTION odontogram_event_guard()"
    )

    # Legenda: tipo e escopo (e código) não mudam depois que o item foi usado.
    op.execute(
        """
        CREATE FUNCTION tooth_status_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.kind <> OLD.kind OR NEW.scope <> OLD.scope OR NEW.code <> OLD.code
                    OR NEW.clinic_id <> OLD.clinic_id)
                    AND EXISTS (SELECT 1 FROM odontogram_events WHERE status_id = OLD.id) THEN
                RAISE EXCEPTION 'tipo, escopo e código de item usado no odontograma não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_tooth_status_guard BEFORE UPDATE ON tooth_statuses "
        "FOR EACH ROW EXECUTE FUNCTION tooth_status_guard()"
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Histórico clínico: append-only. Legenda: só desativar, nunca apagar.
    op.execute(_revoke("UPDATE, DELETE, TRUNCATE", "odontogram_events"))
    op.execute(_revoke("DELETE, TRUNCATE", "tooth_statuses"))


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.execute("DROP TRIGGER trg_odontogram_event_guard ON odontogram_events")
    op.execute("DROP FUNCTION odontogram_event_guard()")
    op.drop_table("odontogram_events")
    op.execute("DROP TRIGGER trg_tooth_status_guard ON tooth_statuses")
    op.execute("DROP FUNCTION tooth_status_guard()")
    op.drop_table("tooth_statuses")
