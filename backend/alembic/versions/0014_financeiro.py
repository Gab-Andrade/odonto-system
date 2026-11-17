"""financeiro: contas a receber, recebimentos (append-only, estorno) e contas a pagar

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "odonto_app"
METHODS = ("dinheiro", "pix", "debito", "credito", "boleto", "transferencia")
KINDS = ("entrada", "parcela", "avulsa")
PAYABLE_STATUSES = ("aberta", "paga", "cancelada")
TENANT_TABLES = ("receivables", "payments", "payables")


def _clinic_id() -> sa.Column:
    return sa.Column(
        "clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"))


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "receivables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid()),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("installment_number", sa.SmallInteger()),
        sa.Column("installment_count", sa.SmallInteger()),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.String(300)),
        _user("created_by"),
        _now("created_at"),
        _now("updated_at"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_receivables_id_clinic"),
        sa.UniqueConstraint("id", "patient_id", "clinic_id", name="uq_receivables_id_patient"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_receivables_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "patient_id", "clinic_id"],
            ["treatment_plans.id", "treatment_plans.patient_id", "treatment_plans.clinic_id"],
            name="fk_receivables_plan_same_patient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("kind", KINDS), name="kind_valid"),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint(
            "(kind = 'parcela') = "
            "(installment_number IS NOT NULL AND installment_count IS NOT NULL)",
            name="installment_numbers",
        ),
        sa.CheckConstraint(
            "installment_number IS NULL OR installment_number BETWEEN 1 AND installment_count",
            name="installment_in_range",
        ),
        sa.CheckConstraint("(kind = 'avulsa') = (plan_id IS NULL)", name="plan_unless_avulsa"),
    )
    op.create_index("ix_receivables_clinic_id", "receivables", ["clinic_id"])
    op.create_index("ix_receivables_due", "receivables", ["clinic_id", "due_date"])
    op.create_index("ix_receivables_patient", "receivables", ["patient_id", "due_date"])
    op.create_index("ix_receivables_plan", "receivables", ["plan_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("receivable_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("fee_pct", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("fee_amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("reversal_of", sa.Uuid()),
        sa.Column("notes", sa.String(300)),
        _user("recorded_by"),
        _now("created_at"),
        sa.UniqueConstraint("id", "receivable_id", "clinic_id", name="uq_payments_id_receivable"),
        sa.ForeignKeyConstraint(
            ["receivable_id", "patient_id", "clinic_id"],
            ["receivables.id", "receivables.patient_id", "receivables.clinic_id"],
            name="fk_payments_receivable_same_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_of", "receivable_id", "clinic_id"],
            ["payments.id", "payments.receivable_id", "payments.clinic_id"],
            name="fk_payments_reversal_same_receivable",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("method", METHODS), name="method_valid"),
        sa.CheckConstraint("(reversal_of IS NULL) = (amount > 0)", name="sign_by_kind"),
        sa.CheckConstraint("fee_pct BETWEEN 0 AND 100", name="fee_range"),
        sa.CheckConstraint("net_amount = amount - fee_amount", name="net_is_amount_minus_fee"),
        # Taxa com o mesmo sinal do valor e nunca maior que ele.
        sa.CheckConstraint(
            "(reversal_of IS NULL AND fee_amount >= 0) "
            "OR (reversal_of IS NOT NULL AND fee_amount <= 0)",
            name="fee_sign",
        ),
        sa.CheckConstraint("abs(fee_amount) <= abs(amount)", name="fee_not_above_amount"),
    )
    op.create_index("ix_payments_clinic_id", "payments", ["clinic_id"])
    op.create_index("ix_payments_receivable", "payments", ["receivable_id"])
    op.create_index("ix_payments_paid_on", "payments", ["clinic_id", "paid_on"])
    op.create_index(
        "uq_payments_one_reversal",
        "payments",
        ["reversal_of"],
        unique=True,
        postgresql_where=sa.text("reversal_of IS NOT NULL"),
    )

    op.create_table(
        "payables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _clinic_id(),
        sa.Column("supplier", sa.String(150), nullable=False),
        sa.Column("category", sa.String(80)),
        sa.Column("description", sa.String(300)),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), server_default="aberta", nullable=False),
        sa.Column("paid_on", sa.Date()),
        sa.Column("paid_method", sa.String(20)),
        sa.Column("cancel_reason", sa.String(300)),
        _user("created_by"),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(_in("status", PAYABLE_STATUSES), name="status_valid"),
        sa.CheckConstraint(
            f"paid_method IS NULL OR {_in('paid_method', METHODS)}", name="paid_method_valid"
        ),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint(
            "(status = 'paga') = (paid_on IS NOT NULL AND paid_method IS NOT NULL)",
            name="paid_fields_when_paid",
        ),
    )
    op.create_index("ix_payables_clinic_id", "payables", ["clinic_id"])
    op.create_index("ix_payables_due", "payables", ["clinic_id", "due_date"])

    # Recebimento: total recebido entre zero e o valor; conta cancelada não recebe;
    # estorno anula exatamente um recebimento. Trava a conta (FOR UPDATE) para que dois
    # recebimentos simultâneos não passem juntos do saldo.
    op.execute(
        """
        CREATE FUNCTION payment_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            r_amount numeric;
            r_cancelled timestamptz;
            o_amount numeric;
            o_fee numeric;
            o_reversal uuid;
            received numeric;
        BEGIN
            SELECT amount, cancelled_at INTO r_amount, r_cancelled
                FROM receivables WHERE id = NEW.receivable_id FOR UPDATE;
            IF NEW.reversal_of IS NULL THEN
                IF r_cancelled IS NOT NULL THEN
                    RAISE EXCEPTION 'conta cancelada não recebe pagamento'
                        USING ERRCODE = 'check_violation';
                END IF;
            ELSE
                SELECT amount, fee_amount, reversal_of INTO o_amount, o_fee, o_reversal
                    FROM payments WHERE id = NEW.reversal_of;
                IF o_reversal IS NOT NULL OR NEW.amount <> -o_amount
                        OR NEW.fee_amount <> -o_fee THEN
                    RAISE EXCEPTION 'estorno não confere com o recebimento'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;
            SELECT COALESCE(SUM(amount), 0) + NEW.amount INTO received
                FROM payments WHERE receivable_id = NEW.receivable_id;
            IF received < 0 OR received > r_amount THEN
                RAISE EXCEPTION 'recebido fora do valor da conta'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_payment_guard BEFORE INSERT ON payments "
        "FOR EACH ROW EXECUTE FUNCTION payment_guard()"
    )

    # Conta: paciente, plano e clínica nunca mudam; com recebimento, valor e vencimento
    # também não; cancelada não volta; só cancela com saldo recebido zero.
    op.execute(
        """
        CREATE FUNCTION receivable_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            has_payments boolean;
            received numeric;
        BEGIN
            IF NEW.patient_id <> OLD.patient_id OR NEW.clinic_id <> OLD.clinic_id
                    OR NEW.plan_id IS DISTINCT FROM OLD.plan_id OR NEW.kind <> OLD.kind THEN
                RAISE EXCEPTION 'paciente, plano e tipo da conta não mudam'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.cancelled_at IS NOT NULL THEN
                RAISE EXCEPTION 'conta cancelada não muda'
                    USING ERRCODE = 'check_violation';
            END IF;
            SELECT count(*) > 0, COALESCE(SUM(amount), 0) INTO has_payments, received
                FROM payments WHERE receivable_id = OLD.id;
            IF has_payments AND (NEW.amount <> OLD.amount OR NEW.due_date <> OLD.due_date) THEN
                RAISE EXCEPTION 'conta com recebimento não muda valor nem vencimento'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.cancelled_at IS NOT NULL AND received <> 0 THEN
                RAISE EXCEPTION 'conta com saldo recebido não é cancelada'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_receivable_guard BEFORE UPDATE ON receivables "
        "FOR EACH ROW EXECUTE FUNCTION receivable_guard()"
    )

    # Conta a pagar paga ou cancelada não muda mais.
    op.execute(
        """
        CREATE FUNCTION payable_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status <> 'aberta' OR NEW.clinic_id <> OLD.clinic_id THEN
                RAISE EXCEPTION 'conta a pagar paga ou cancelada não muda'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_payable_guard BEFORE UPDATE ON payables "
        "FOR EACH ROW EXECUTE FUNCTION payable_guard()"
    )

    for table in TENANT_TABLES:
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)

    # Dinheiro não se apaga: recebimento é append-only; contas só cancelam.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON payments FROM {APP_ROLE};
                REVOKE DELETE, TRUNCATE ON receivables FROM {APP_ROLE};
                REVOKE DELETE, TRUNCATE ON payables FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in disable_tenant_rls(table):
            op.execute(stmt)
    op.execute("DROP TRIGGER trg_receivable_guard ON receivables")
    op.execute("DROP FUNCTION receivable_guard()")
    op.execute("DROP TRIGGER trg_payment_guard ON payments")
    op.execute("DROP FUNCTION payment_guard()")
    op.execute("DROP TRIGGER trg_payable_guard ON payables")
    op.execute("DROP FUNCTION payable_guard()")
    op.drop_table("payables")
    op.drop_table("payments")
    op.drop_table("receivables")
