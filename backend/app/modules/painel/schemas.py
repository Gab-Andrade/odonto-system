"""Saídas do painel. Cada campo diz de onde o número vem."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class AgendaOut(BaseModel):
    """Consultas com início no dia (bloqueios não contam)."""

    total: int
    agendado: int = Field(description="Ainda sem confirmação.")
    confirmado: int
    atendido: int
    falta: int
    cancelado: int


class RevenueOut(BaseModel):
    received: Decimal = Field(description="Recebimentos com data no mês, já com estornos.")
    received_net: Decimal = Field(description="O recebido menos as taxas de cartão.")
    expected: Decimal = Field(description="Contas a receber com vencimento no mês.")


class OverdueOut(BaseModel):
    count: int = Field(description="Contas a receber vencidas com saldo.")
    amount: Decimal = Field(description="Saldo em aberto dessas contas.")


class PayablesOut(BaseModel):
    overdue_count: int
    overdue_amount: Decimal
    soon_count: int = Field(description="Contas a pagar que vencem nos próximos 7 dias.")
    soon_amount: Decimal


class QuotesOut(BaseModel):
    awaiting: int = Field(description="Orçamentos emitidos aguardando decisão.")
    awaiting_stale: int = Field(description="Desses, emitidos há mais de 7 dias.")
    issued_in_month: int
    approved_in_month: int = Field(description="Decididos no mês com algum item aprovado.")
    approved_value_in_month: Decimal = Field(
        description="Soma dos itens aprovados desses orçamentos, pelo preço congelado (sem "
        "desconto)."
    )


class StockOut(BaseModel):
    below_minimum: int = Field(description="Materiais ativos abaixo do estoque mínimo.")
    expired_lots: int = Field(description="Lotes vencidos que ainda têm saldo.")
    expiring_lots: int = Field(description="Lotes que vencem em até 30 dias.")


class ProductionOut(BaseModel):
    dentist_id: uuid.UUID
    dentist_name: str | None = None
    procedures: int = Field(description="Itens do plano realizados no mês.")
    value: Decimal = Field(description="Valor desses itens, preço congelado com o desconto.")


class OverviewOut(BaseModel):
    day: date
    month: date
    agenda: AgendaOut
    revenue: RevenueOut
    overdue: OverdueOut
    payables: PayablesOut
    quotes: QuotesOut
    stock: StockOut
    production: list[ProductionOut] = Field(description="Por dentista, no mês.")
    comparison: dict[str, Decimal | None] = Field(
        default_factory=dict, description="Variação % dos indicadores contra o mês anterior."
    )
    goals: list["GoalOut"] = Field(default_factory=list, description="Metas da clínica.")
    alerts: "AlertsSummaryOut | None" = None


class SettlementBrief(BaseModel):
    period_end: date
    total: Decimal


class MyPerformanceOut(BaseModel):
    dentist_id: uuid.UUID
    day: date
    month: date
    agenda_today: AgendaOut
    encounters: int = Field(description="Atendimentos abertos no mês.")
    production: ProductionOut
    quotes: QuotesOut = Field(description="Orçamentos em que é o responsável.")
    last_settlement: SettlementBrief | None = Field(description="Último repasse fechado.")
    comparison: dict[str, Decimal | None] = Field(
        default_factory=dict, description="Variação % dos próprios números contra o mês anterior."
    )
    goals: list["GoalOut"] = Field(default_factory=list, description="As próprias metas.")
    alerts: "AlertsSummaryOut | None" = Field(
        None, description="Alertas em que é o dentista responsável."
    )


# ---------- Fase 5.2: indicadores do mês, tendências, equipe, metas e alertas ----------


class MonthMetricsOut(BaseModel):
    month: date
    recebido: Decimal | None = Field(description="Recebimentos no mês (só na clínica).")
    producao: Decimal = Field(description="Valor dos procedimentos realizados (com desconto).")
    procedimentos: int = Field(description="Procedimentos realizados no mês.")
    aprovado: Decimal = Field(
        description="Itens aprovados dos orçamentos decididos no mês (preço congelado)."
    )
    orcamentos_emitidos: int
    orcamentos_decididos: int = Field(description="Aprovados + recusados no mês.")
    orcamentos_aprovados: int
    conversao_pct: Decimal | None = Field(description="Aprovados ÷ decididos (%).")
    ticket_medio: Decimal | None = Field(description="Valor aprovado ÷ orçamentos aprovados.")
    consultas: int = Field(description="Consultas no mês, sem as canceladas.")
    faltas: int
    taxa_faltas_pct: Decimal | None = Field(description="Faltas ÷ (atendidas + faltas) (%).")
    atendimentos: int = Field(description="Atendimentos abertos no mês.")
    novos_pacientes: int | None = Field(description="Cadastros no mês (só na clínica).")


class TrendPointOut(BaseModel):
    metrics: MonthMetricsOut
    variation_pct: dict[str, Decimal | None] = Field(
        description="Variação % de cada indicador contra o mês anterior (null sem base)."
    )


class TrendOut(BaseModel):
    dentist_id: uuid.UUID | None
    months: list[TrendPointOut] = Field(description="Do mais antigo ao mais recente.")


class GoalIn(BaseModel):
    month: date = Field(description="Qualquer dia do mês; é guardado como dia 1.")
    metric: str = Field(description="recebido, producao, procedimentos ou aprovado.")
    dentist_id: uuid.UUID | None = Field(None, description="Vazio: meta da clínica.")
    target: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class GoalOut(BaseModel):
    id: uuid.UUID
    month: date
    metric: str
    dentist_id: uuid.UUID | None
    target: Decimal
    achieved: Decimal | None = Field(None, description="Realizado no mês até agora.")
    pct: Decimal | None = Field(None, description="Realizado ÷ meta (%).")


class TeamMemberOut(BaseModel):
    dentist_id: uuid.UUID
    name: str
    role: str
    metrics: MonthMetricsOut
    goals: list[GoalOut]


class TeamOut(BaseModel):
    month: date
    members: list[TeamMemberOut]


class AlertsSummaryOut(BaseModel):
    total: int
    by_rule: dict[str, int] = Field(description="Alertas ativos por regra (ver /inteligencia).")


OverviewOut.model_rebuild()
MyPerformanceOut.model_rebuild()
