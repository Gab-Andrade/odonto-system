"""Estoque — versão mínima: cadastro de materiais com custo unitário.

Serve hoje à precificação por custo (ficha técnica → custo de materiais do procedimento).
Lotes, validade, entradas/saídas e baixa automática entram na Fase 3, neste mesmo módulo;
o custo unitário passará a vir dos lotes, sem mudar quem o consome (via service).

Material não é excluído, só desativado: fichas técnicas apontam para ele.
"""

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Numeric, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class Material(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_materials_id_clinic"),
        UniqueConstraint("clinic_id", "name", name="uq_materials_clinic_name"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(150))
    unit: Mapped[str] = mapped_column(String(20))  # ex.: un, ml, g, cx, par, tubo
    category: Mapped[str | None] = mapped_column(String(100))
    # 4 casas: materiais são comprados em caixa e usados em frações (ex.: R$ 0,0350 por ml).
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
