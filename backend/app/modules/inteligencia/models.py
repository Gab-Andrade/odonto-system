"""Inteligência clínica, fase de alertas por regra.

Os alertas não são guardados: são calculados na hora a partir de agenda, plano de
tratamento, atendimentos e financeiro. Ficam no banco só:

- `alert_rule_settings`: a configuração da clínica para cada regra (ligada ou não e os
  parâmetros). Sem linha, a regra vale com os padrões do catálogo (`regras.RULES`).
- `alert_dismissals`: "dispensar até tal data" um alerta específico (ex.: a recepção já
  ligou para o paciente). Append-only; vale o registro mais recente de cada alerta.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class AlertRuleSetting(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "alert_rule_settings"
    __table_args__ = (UniqueConstraint("clinic_id", "code", name="uq_alert_rule_settings_code"),)

    code: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class AlertDismissal(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "alert_dismissals"
    __table_args__ = (Index("ix_alert_dismissals_lookup", "code", "alert_key", "created_at"),)

    code: Mapped[str] = mapped_column(String(50))
    # Identifica o alerta dentro da regra (paciente, plano ou atendimento).
    alert_key: Mapped[str] = mapped_column(String(80))
    until: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
