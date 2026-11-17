"""Regras puras do estoque (testáveis sem banco)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

QTY = Decimal("0.0001")
NEAR_EXPIRY_DAYS = 30


class StockRuleError(ValueError):
    pass


def qty(value: Decimal) -> Decimal:
    return Decimal(value).quantize(QTY)


@dataclass(frozen=True)
class LotBalance:
    lot_id: uuid.UUID
    balance: Decimal
    expires_on: date | None
    received_on: date
    unit_cost: Decimal


def fefo_order(lots: list[LotBalance]) -> list[LotBalance]:
    """Primeiro o que vence primeiro; sem validade por último; empate pelo mais antigo."""
    return sorted(
        lots,
        key=lambda lot: (lot.expires_on is None, lot.expires_on or date.max, lot.received_on),
    )


def allocate(
    lots: list[LotBalance], needed: Decimal, today: date
) -> tuple[list[tuple[uuid.UUID, Decimal]], Decimal]:
    """Tira `needed` dos lotes com saldo e não vencidos, em ordem FEFO.

    Devolve [(lote, quantidade)] e o que faltou (0 quando deu tudo).
    """
    remaining = qty(needed)
    taken: list[tuple[uuid.UUID, Decimal]] = []
    usable = [
        lot
        for lot in lots
        if lot.balance > 0 and (lot.expires_on is None or lot.expires_on >= today)
    ]
    for lot in fefo_order(usable):
        if remaining <= 0:
            break
        part = min(lot.balance, remaining)
        taken.append((lot.lot_id, qty(part)))
        remaining -= part
    return taken, qty(max(remaining, Decimal("0")))


def weighted_cost(lots: list[LotBalance]) -> Decimal | None:
    """Custo médio ponderado dos lotes com saldo; None quando não há saldo."""
    total_qty = sum((lot.balance for lot in lots if lot.balance > 0), Decimal("0"))
    if total_qty <= 0:
        return None
    total_value = sum(
        (lot.balance * lot.unit_cost for lot in lots if lot.balance > 0), Decimal("0")
    )
    return (total_value / total_qty).quantize(QTY)


def expiry_status(expires_on: date | None, today: date, days: int = NEAR_EXPIRY_DAYS) -> str:
    if expires_on is None:
        return "sem_validade"
    if expires_on < today:
        return "vencido"
    if (expires_on - today).days <= days:
        return "vence_em_breve"
    return "ok"
