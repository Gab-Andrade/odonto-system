"""estoque: lotes com validade, movimentos append-only e estoque mínimo

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
KINDS = ("entrada", "consumo", "saida", "ajuste")
TENANT_TABLES = ("stock_lots", "stock_movements")


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("materials", sa.Column("min_quantity", sa.Numeric(12, 4)))
    op.create_check_constraint(
        "min_quantity_non_negative", "materials", "min_quantity IS NULL OR min_quantity >= 0"
    )
    # Alvo da FK composta dos movimentos (consumo ligado ao item do plano).
    op.create_unique_constraint(
        "uq_treatment_plan_items_id_clinic", "treatment_plan_items", ["id", "clinic_id"]
    )

    op.create_table(
        "stock_lots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("lot_code", sa.String(60)),
        sa.Column("expires_on", sa.Date()),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("supplier", sa.String(150)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("id", "clinic_id", name="uq_stock_lots_id_clinic"),
        sa.UniqueConstraint("id", "material_id", "clinic_id", name="uq_stock_lots_id_material"),
        sa.ForeignKeyConstraint(
            ["material_id", "clinic_id"],
            ["materials.id", "materials.clinic_id"],
            name="fk_stock_lots_material_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )
    op.create_index("ix_stock_lots_clinic_id", "stock_lots", ["clinic_id"])
    op.create_index("ix_stock_lots_material", "stock_lots", ["material_id", "expires_on"])
    op.create_index("ix_stock_lots_expires", "stock_lots", ["clinic_id", "expires_on"])

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("reason", sa.String(300)),
        sa.Column("patient_id", sa.Uuid()),
        sa.Column("plan_item_id", sa.Uuid()),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        # clock_timestamp(): ordem real dos movimentos dentro de uma mesma transação.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lot_id", "material_id", "clinic_id"],
            ["stock_lots.id", "stock_lots.material_id", "stock_lots.clinic_id"],
            name="fk_stock_movements_lot_same_material",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_stock_movements_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_item_id", "clinic_id"],
            ["treatment_plan_items.id", "treatment_plan_items.clinic_id"],
            name="fk_stock_movements_plan_item_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("kind", KINDS), name="kind_valid"),
        sa.CheckConstraint("quantity <> 0", name="quantity_not_zero"),
        sa.CheckConstraint(
            "(kind = 'entrada' AND quantity > 0) OR (kind IN ('consumo', 'saida') AND quantity < 0)"
            " OR kind = 'ajuste'",
            name="sign_by_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'consumo') = (patient_id IS NOT NULL AND plan_item_id IS NOT NULL)",
            name="consumption_has_patient",
        ),
        sa.CheckConstraint(
            "kind NOT IN ('saida', 'ajuste') OR reason IS NOT NULL", name="manual_has_reason"
        ),
    )
    op.create_index("ix_stock_movements_clinic_id", "stock_movements", ["clinic_id"])
    op.create_index("ix_stock_movements_lot", "stock_movements", ["lot_id", "created_at"])
    op.create_index("ix_stock_movements_material", "stock_movements", ["material_id", "created_at"])
    op.create_index("ix_stock_movements_patient", "stock_movements", ["patient_id"])

    # Saldo do lote nunca negativo (trava o lote: movimentos simultâneos não passam juntos).
    op.execute(
        """
        CREATE FUNCTION stock_movement_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            balance numeric;
        BEGIN
            PERFORM 1 FROM stock_lots WHERE id = NEW.lot_id FOR UPDATE;
            SELECT COALESCE(SUM(quantity), 0) + NEW.quantity INTO balance
                FROM stock_movements WHERE lot_id = NEW.lot_id;
            IF balance < 0 THEN
                RAISE EXCEPTION 'saldo do lote ficaria negativo'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_stock_movement_guard BEFORE INSERT ON stock_movements "
        "FOR EACH ROW EXECUTE FUNCTION stock_movement_guard()"
    )
    # Lote não troca de material nem de custo (o custo é o da compra).
    op.execute(
        """
        CREATE FUNCTION stock_lot_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.material_id <> OLD.material_id OR NEW.unit_cost <> OLD.unit_cost
                    OR NEW.clinic_id <> OLD.clinic_id THEN
                RAISE EXCEPTION 'lote não muda material nem custo'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_stock_lot_guard BEFORE UPDATE ON stock_lots "
        "FOR EACH ROW EXECUTE FUNCTION stock_lot_guard()"
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE ON stock_movements FROM {APP_ROLE};
                REVOKE DELETE ON stock_lots FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.execute("DROP TRIGGER trg_stock_lot_guard ON stock_lots")
    op.execute("DROP FUNCTION stock_lot_guard()")
    op.execute("DROP TRIGGER trg_stock_movement_guard ON stock_movements")
    op.execute("DROP FUNCTION stock_movement_guard()")
    op.drop_table("stock_movements")
    op.drop_table("stock_lots")
    op.drop_constraint("uq_treatment_plan_items_id_clinic", "treatment_plan_items", type_="unique")
    op.drop_constraint("min_quantity_non_negative", "materials", type_="check")
    op.drop_column("materials", "min_quantity")
