from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.precificacao.schemas import ItemsReplace
from app.modules.precificacao.service import RuleViolation, apply_adjustment, check_valid_from


@pytest.mark.parametrize(
    ("price", "pct", "expected"),
    [
        ("100.00", "15", "115.00"),
        ("100.00", "-10", "90.00"),
        ("33.33", "10", "36.66"),  # 36.663
        ("1.00", "0.5", "1.01"),  # 1.005 → meio para cima
        ("250.00", None, "250.00"),
        ("0.00", "50", "0.00"),
    ],
)
def test_apply_adjustment(price, pct, expected):
    result = apply_adjustment(Decimal(price), Decimal(pct) if pct else None)
    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


def test_valid_from_rules():
    today = date(2026, 11, 16)
    check_valid_from(today, today, None)
    check_valid_from(date(2026, 12, 1), today, date(2026, 11, 20))
    with pytest.raises(RuleViolation, match="passado"):
        check_valid_from(date(2026, 11, 15), today, None)
    with pytest.raises(RuleViolation, match="última versão"):
        check_valid_from(date(2026, 11, 18), today, date(2026, 11, 20))


def test_items_reject_duplicate_codes():
    item = {"procedure_code": "RESTAURACAO", "description": "Restauração", "price": "150.00"}
    with pytest.raises(ValidationError, match="repetidos: RESTAURACAO"):
        ItemsReplace(items=[item, {**item, "price": "160.00"}])


def test_items_reject_negative_and_too_many_decimals():
    with pytest.raises(ValidationError):
        ItemsReplace(items=[{"procedure_code": "X", "description": "X", "price": "-1"}])
    with pytest.raises(ValidationError):
        ItemsReplace(items=[{"procedure_code": "X", "description": "X", "price": "1.234"}])
