from datetime import date
from decimal import Decimal

from app.modules.painel import gestao


def test_variation():
    assert gestao.variation(Decimal("150"), Decimal("100")) == Decimal("50.0")
    assert gestao.variation(50, 100) == Decimal("-50.0")
    assert gestao.variation(10, 0) is None
    assert gestao.variation(None, 10) is None


def test_ratio_pct():
    assert gestao.ratio_pct(1, 3) == Decimal("33.3")
    assert gestao.ratio_pct(0, 0) is None
    assert gestao.ratio_pct_decimal(Decimal("500"), Decimal("1000")) == Decimal("50.0")
    assert gestao.ratio_pct_decimal(None, Decimal("10")) is None


def test_months_back_crosses_year():
    assert gestao.months_back(date(2026, 2, 15), 4) == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
