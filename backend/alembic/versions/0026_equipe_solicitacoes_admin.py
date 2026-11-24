"""equipe: cadastro pela clínica, troca obrigatória de senha, convites e pedidos de admin

- `users.must_change_password`: senha aleatória (cadastro ou redefinição) só serve para
  definir a própria senha. `users.password_changed_at`: tokens emitidos antes da última
  troca deixam de valer.
- `membership_invites` (global, como `clinic_memberships`): vínculo de um e-mail que já
  tem cadastro só passa a valer quando a pessoa digita o código de uso único que a
  clínica entregou. Global porque o aceite acontece antes de haver clínica na sessão; o
  isolamento é na camada de serviço.
- `admin_change_requests` (da clínica, com RLS): rebaixar ou desativar um administrador
  só vale quando o próprio administrador alvo aceita.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REQUESTS = "admin_change_requests"
INVITES = "membership_invites"
ROLES = ("admin", "gestor", "dentista", "asb", "recepcao")
ACTIONS = ("rebaixar", "desativar")
STATUSES = ("pendente", "aprovada", "recusada", "cancelada", "expirada")
# Papel de destino de um rebaixamento: qualquer um, menos admin.
NEW_ROLES = ("gestor", "dentista", "asb", "recepcao")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True)))

    op.create_table(
        INVITES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "clinic_id",
            sa.Uuid(),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "clinic_id", name="uq_invite_user_clinic"),
        sa.CheckConstraint(_in("role", ROLES), name="role_valid"),
    )
    op.create_index(f"ix_{INVITES}_clinic_id", INVITES, ["clinic_id"])

    op.create_table(
        REQUESTS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.Uuid(),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("new_role", sa.String(20)),
        sa.Column("reason", sa.String(300)),
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(_in("action", ACTIONS), name="action_valid"),
        sa.CheckConstraint(_in("status", STATUSES), name="status_valid"),
        sa.CheckConstraint(
            "new_role IS NULL OR " + _in("new_role", NEW_ROLES), name="new_role_valid"
        ),
        # Rebaixar diz para qual papel; desativar não tem papel novo.
        sa.CheckConstraint(
            "(action = 'rebaixar') = (new_role IS NOT NULL)", name="new_role_matches_action"
        ),
        sa.CheckConstraint("requested_by <> target_user_id", name="not_self"),
        # Só o próprio administrador alvo aceita.
        sa.CheckConstraint(
            "status <> 'aprovada' OR decided_by = target_user_id", name="accepted_by_target"
        ),
        sa.CheckConstraint(
            "(status = 'pendente') = (decided_at IS NULL)", name="decided_when_closed"
        ),
    )
    op.create_index(f"ix_{REQUESTS}_clinic_id", REQUESTS, ["clinic_id"])
    # No máximo uma solicitação pendente por administrador alvo.
    op.create_index(
        f"uq_{REQUESTS}_pending_target",
        REQUESTS,
        ["clinic_id", "target_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pendente'"),
    )
    for stmt in enable_tenant_rls(REQUESTS):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in disable_tenant_rls(REQUESTS):
        op.execute(stmt)
    op.drop_index(f"uq_{REQUESTS}_pending_target", table_name=REQUESTS)
    op.drop_index(f"ix_{REQUESTS}_clinic_id", table_name=REQUESTS)
    op.drop_table(REQUESTS)
    op.drop_index(f"ix_{INVITES}_clinic_id", table_name=INVITES)
    op.drop_table(INVITES)
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "must_change_password")
