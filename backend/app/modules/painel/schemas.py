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
