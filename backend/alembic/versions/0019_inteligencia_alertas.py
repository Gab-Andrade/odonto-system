"""inteligência: configuração das regras de alerta e alertas dispensados (append-only)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
CODES = (
    "profilaxia_atrasada",
    "canal_sem_retorno",
    "orcamento_aprovado_sem_agendamento",
    "orcamento_sem_resposta",
    "atendimento_aberto",
    "faltas_repetidas",
    "conta_em_atraso",
)
CODE_CHECK = "code IN (" + ", ".join(f"'{c}'" for c in CODES) + ")"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _clinic() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "alert_rule_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("clinic_id", "code", name="uq_alert_rule_settings_code"),
        sa.CheckConstraint(CODE_CHECK, name="code_valid"),
        sa.CheckConstraint("jsonb_typeof(params) = 'object'", name="params_object"),
    )
    op.create_index("ix_alert_rule_settings_clinic_id", "alert_rule_settings", ["clinic_id"])

    op.create_table(
        "alert_dismissals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("alert_key", sa.String(80), nullable=False),
        sa.Column("until", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(300)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        # clock_timestamp(): vale o mais recente de cada alerta, na ordem real.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(CODE_CHECK, name="code_valid"),
    )
    op.create_index("ix_alert_dismissals_clinic_id", "alert_dismissals", ["clinic_id"])
    op.create_index(
        "ix_alert_dismissals_lookup", "alert_dismissals", ["code", "alert_key", "created_at"]
    )

    for table in ("alert_rule_settings", "alert_dismissals"):
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Histórico de quem dispensou o quê: append-only (voltar a mostrar = novo registro).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON alert_dismissals FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in ("alert_dismissals", "alert_rule_settings"):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
        op.drop_table(table)
