"""repasse: regras de comissão por dentista e fechamentos append-only

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
TENANT_TABLES = ("commission_rules", "commission_settlements", "commission_lines")


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "commission_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column(
            "dentist_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("procedure_code", sa.String(40)),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("deduct_materials", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("deduct_card_fee", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        _now("created_at"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_commission_rules_id_clinic"),
        sa.CheckConstraint("kind IN ('percentual', 'fixo')", name="kind_valid"),
        sa.CheckConstraint(
            "value >= 0 AND (kind <> 'percentual' OR value <= 100)", name="value_range"
        ),
    )
    op.create_index("ix_commission_rules_clinic_id", "commission_rules", ["clinic_id"])
    op.create_index(
        "ix_commission_rules_lookup",
        "commission_rules",
        ["dentist_id", "procedure_code", "valid_from"],
    )

    op.create_table(
        "commission_settlements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column(
            "dentist_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.String(300)),
        sa.Column("closed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        _now("closed_at"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_commission_settlements_id_clinic"),
        sa.UniqueConstraint(
            "clinic_id", "dentist_id", "period_end", name="uq_commission_settlements_dentist_end"
        ),
        sa.CheckConstraint(
            "period_start IS NULL OR period_start <= period_end", name="period_valid"
        ),
    )
    op.create_index("ix_commission_settlements_clinic_id", "commission_settlements", ["clinic_id"])

    op.create_table(
        "commission_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("settlement_id", sa.Uuid(), nullable=False),
        sa.Column("plan_item_id", sa.Uuid(), nullable=False),
        sa.Column("procedure_code", sa.String(40), nullable=False),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("fee_deduction", sa.Numeric(12, 2), nullable=False),
        sa.Column("material_deduction", sa.Numeric(12, 2), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("commission", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["settlement_id", "clinic_id"],
            ["commission_settlements.id", "commission_settlements.clinic_id"],
            name="fk_commission_lines_settlement_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_item_id", "clinic_id"],
            ["treatment_plan_items.id", "treatment_plan_items.clinic_id"],
            name="fk_commission_lines_plan_item_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id", "clinic_id"],
            ["commission_rules.id", "commission_rules.clinic_id"],
            name="fk_commission_lines_rule_same_clinic",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_commission_lines_clinic_id", "commission_lines", ["clinic_id"])
    op.create_index("ix_commission_lines_item", "commission_lines", ["plan_item_id"])
    op.create_index("ix_commission_lines_settlement", "commission_lines", ["settlement_id"])

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Regras e fechamentos são histórico: nada se altera nem se apaga.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE ON commission_rules FROM {APP_ROLE};
                REVOKE UPDATE, DELETE ON commission_settlements FROM {APP_ROLE};
                REVOKE UPDATE, DELETE ON commission_lines FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.drop_table("commission_lines")
    op.drop_table("commission_settlements")
    op.drop_table("commission_rules")
