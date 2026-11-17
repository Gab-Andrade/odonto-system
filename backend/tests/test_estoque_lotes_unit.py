"""Estoque por lote: FEFO, alocação, custo médio e validade (sem banco)."""

import uuid
from datetime import date
from decimal import Decimal

from app.modules.estoque.regras import (
    LotBalance,
    allocate,
    expiry_status,
    fefo_order,
    weighted_cost,
)

D = Decimal
TODAY = date(2026, 11, 17)
A, B, C, E = (uuid.UUID(int=i) for i in range(1, 5))


def _lot(lot_id, balance, expires, received=date(2026, 1, 1), cost="1.00"):
    return LotBalance(lot_id, D(balance), expires, received, D(cost))


def test_fefo_order_expiring_first_and_no_expiry_last():
    lots = [
        _lot(A, "5", None),
        _lot(B, "5", date(2027, 6, 1)),
        _lot(C, "5", date(2027, 1, 1)),
        _lot(E, "5", date(2027, 1, 1), received=date(2025, 12, 1)),
    ]
    assert [lot.lot_id for lot in fefo_order(lots)] == [E, C, B, A]


def test_allocate_spreads_across_lots_and_skips_expired():
    lots = [
        _lot(A, "3", date(2026, 12, 1)),
        _lot(B, "10", date(2027, 6, 1)),
        _lot(C, "50", date(2026, 11, 16)),  # vencido ontem: não sai
        _lot(E, "0", date(2026, 11, 20)),  # sem saldo
    ]
    taken, missing = allocate(lots, D("5"), TODAY)
    assert taken == [(A, D("3.0000")), (B, D("2.0000"))] and missing == 0
    taken, missing = allocate(lots, D("20"), TODAY)
    assert sum(q for _, q in taken) == D("13") and missing == D("7.0000")
    assert allocate([], D("1"), TODAY) == ([], D("1.0000"))


def test_weighted_cost():
    lots = [
        _lot(A, "10", None, cost="2.00"),
        _lot(B, "30", None, cost="4.00"),
        _lot(C, "0", None, cost="99"),
    ]
    assert weighted_cost(lots) == D("3.5000")
    assert weighted_cost([_lot(A, "0", None)]) is None


def test_expiry_status():
    assert expiry_status(None, TODAY) == "sem_validade"
    assert expiry_status(date(2026, 11, 16), TODAY) == "vencido"
    assert expiry_status(date(2026, 12, 17), TODAY) == "vence_em_breve"
    assert expiry_status(date(2026, 12, 18), TODAY) == "ok"
