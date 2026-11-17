"""odontograma: efeito do item da legenda no modelo 3D (colorir ou ocultar o dente)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISPLAYS = ("colorir", "ocultar")


def upgrade() -> None:
    op.add_column(
        "tooth_statuses",
        sa.Column("display_3d", sa.String(20), server_default="colorir", nullable=False),
    )
    op.create_check_constraint(
        "display_3d_valid",
        "tooth_statuses",
        "display_3d IN (" + ", ".join(f"'{d}'" for d in DISPLAYS) + ")",
    )
    # Ocultar vale para o dente inteiro, não para uma face.
    op.create_check_constraint(
        "display_3d_whole_tooth", "tooth_statuses", "display_3d = 'colorir' OR scope = 'dente'"
    )
    # Legendas já criadas: "ausente" da legenda padrão (código, tipo e escopo do padrão)
    # passa a ocultar o dente no 3D. Item próprio da clínica com esse mesmo código e
    # definição também muda, de propósito (mesmo significado). Sem auditoria: é migração.
    # A tabela tem FORCE ROW LEVEL SECURITY (vale até para o dono); desliga só durante
    # este UPDATE de todas as clínicas, na mesma transação da migração.
    op.execute("ALTER TABLE tooth_statuses NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE tooth_statuses SET display_3d = 'ocultar' "
        "WHERE code = 'ausente' AND kind = 'patologia' AND scope = 'dente'"
    )
    op.execute("ALTER TABLE tooth_statuses FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_constraint("display_3d_whole_tooth", "tooth_statuses", type_="check")
    op.drop_constraint("display_3d_valid", "tooth_statuses", type_="check")
    op.drop_column("tooth_statuses", "display_3d")
