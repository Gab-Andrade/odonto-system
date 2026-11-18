"""Metas do painel do gestor (a única tabela do módulo, que no resto é só leitura).

Uma meta é um valor-alvo de um indicador num mês, para a clínica inteira (sem dentista)
ou para um dentista. Metas são opcionais: o painel funciona sem nenhuma.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class GoalMetric(StrEnum):
    RECEBIDO = "recebido"  # só da clínica: recebimento não é atribuído a dentista
    PRODUCAO = "producao"  # valor dos procedimentos realizados
    PROCEDIMENTOS = "procedimentos"  # quantidade de procedimentos realizados
    APROVADO = "aprovado"  # valor dos orçamentos aprovados no mês


class PanelGoal(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "panel_goals"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "month",
            "metric",
            "dentist_id",
            name="uq_panel_goals_month_metric_dentist",
            postgresql_nulls_not_distinct=True,
        ),
    )

    month: Mapped[date] = mapped_column(Date)  # sempre o dia 1
    metric: Mapped[GoalMetric] = mapped_column(
        Enum(
            GoalMetric,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
            validate_strings=True,
            create_constraint=False,
        )
    )
    dentist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    target: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
