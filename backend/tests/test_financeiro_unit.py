"""Financeiro: parcelamento, meses, taxa e status (sem banco)."""

from datetime import date
from decimal import Decimal

import pytest

from app.modules.financeiro.regras import (
    FinanceRuleError,
    add_months,
    fee,
    receivable_status,
    split,
)

D = Decimal
TODAY = date(2026, 11, 17)


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


def test_split_sums_exactly_with_cents_in_first_installment():
    parts = split(D("1000.00"), down_payment=D("100"), installments=3,
                  down_payment_date=TODAY, first_due_date=date(2026, 12, 17))  # fmt: skip
    assert [(p.kind, p.number, p.amount) for p in parts] == [
        ("entrada", None, D("100.00")),
        ("parcela", 1, D("300.00")),
        ("parcela", 2, D("300.00")),
        ("parcela", 3, D("300.00")),
    ]
    odd = split(D("100.00"), down_payment=D("0"), installments=3,
                down_payment_date=TODAY, first_due_date=TODAY)  # fmt: skip
    assert [p.amount for p in odd] == [D("33.34"), D("33.33"), D("33.33")]
    assert sum(p.amount for p in odd) == D("100.00")
    assert [p.due_date for p in odd] == [TODAY, date(2026, 12, 17), date(2027, 1, 17)]
    cash = split(D("50"), down_payment=D("50"), installments=0,
                 down_payment_date=TODAY, first_due_date=TODAY)  # fmt: skip
    assert [(p.kind, p.amount) for p in cash] == [("entrada", D("50.00"))]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"total": D("0"), "down_payment": D("0"), "installments": 1},
        {"total": D("100"), "down_payment": D("120"), "installments": 1},
        {"total": D("100"), "down_payment": D("0"), "installments": 0},
        {"total": D("100"), "down_payment": D("0"), "installments": 49},
        {"total": D("100"), "down_payment": D("100"), "installments": 2},
        {"total": D("0.05"), "down_payment": D("0"), "installments": 10},
    ],
)
def test_split_rejects(kwargs):
    total = kwargs.pop("total")
    with pytest.raises(FinanceRuleError):
        split(total, down_payment_date=TODAY, first_due_date=TODAY, **kwargs)


def test_split_first_due_not_before_down_payment():
    with pytest.raises(FinanceRuleError):
        split(D("100"), down_payment=D("10"), installments=1,
              down_payment_date=TODAY, first_due_date=date(2026, 11, 1))  # fmt: skip


def test_fee():
    assert fee(D("100.00"), D("3.99")) == (D("3.99"), D("96.01"))
    assert fee(D("33.33"), D("2.5")) == (D("0.83"), D("32.50"))
    with pytest.raises(FinanceRuleError):
        fee(D("10"), D("101"))


def test_receivable_status():
    due_past, due_future = date(2026, 11, 1), date(2026, 12, 1)
    assert receivable_status(D("100"), D("0"), due_future, TODAY, False) == "aberta"
    assert receivable_status(D("100"), D("40"), due_future, TODAY, False) == "parcial"
    assert receivable_status(D("100"), D("40"), due_past, TODAY, False) == "vencida"
    assert receivable_status(D("100"), D("100"), due_past, TODAY, False) == "paga"
    assert receivable_status(D("100"), D("0"), due_past, TODAY, True) == "cancelada"
