"""precificação: erros do último recálculo guardados na versão

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lista de {"procedimento", "erro"} do último recálculo; nulo enquanto não houve cálculo.
    # Publicar com erros exige confirmação explícita.
    op.add_column("price_table_versions", sa.Column("calc_errors", postgresql.JSONB()))
    op.create_check_constraint(
        "calc_errors_only_when_calculated",
        "price_table_versions",
        "calc_errors IS NULL OR calculated_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("calc_errors_only_when_calculated", "price_table_versions", type_="check")
    op.drop_column("price_table_versions", "calc_errors")
