"""odontograma: região do item da legenda (coroa ou raiz)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REGIONS = ("coroa", "raiz")
# Itens que já existem e são da raiz: canal (feito e a fazer), retratamento e lesão
# periapical (os dois últimos vêm da clínica de demonstração ou criados pela clínica).
ROOT_CODES = (
    "endodontia",
    "endodontia_planejada",
    "retratamento",
    "retratamento_planejado",
    "lesao_periapical",
)


def upgrade() -> None:
    op.add_column(
        "tooth_statuses",
        sa.Column("region", sa.String(20), server_default="coroa", nullable=False),
    )
    op.create_check_constraint(
        "region_valid",
        "tooth_statuses",
        "region IN (" + ", ".join(f"'{r}'" for r in REGIONS) + ")",
    )
    # A raiz é do dente inteiro: item por face fica sempre na coroa.
    op.create_check_constraint(
        "region_whole_tooth", "tooth_statuses", "region = 'coroa' OR scope = 'dente'"
    )
    # Legendas já criadas, em todas as clínicas. Mesmo padrão da 0018: a tabela tem FORCE
    # ROW LEVEL SECURITY (vale até para o dono); desliga só durante este UPDATE.
    op.execute("ALTER TABLE tooth_statuses NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE tooth_statuses SET region = 'raiz' WHERE scope = 'dente' AND code IN ("
        + ", ".join(f"'{c}'" for c in ROOT_CODES)
        + ")"
    )
    op.execute("ALTER TABLE tooth_statuses FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_constraint("region_whole_tooth", "tooth_statuses", type_="check")
    op.drop_constraint("region_valid", "tooth_statuses", type_="check")
    op.drop_column("tooth_statuses", "region")
