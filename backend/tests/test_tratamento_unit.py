"""Plano de tratamento: faces, desconto, totais e status (sem banco)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.tratamento.models import ItemStatus as I
from app.modules.tratamento.models import PlanStatus as P
from app.modules.tratamento.regras import (
    PlanRuleError,
    check_discount,
    is_expired,
    normalize_faces,
    plan_after_decision,
    plan_after_items,
    totals,
)
from app.modules.tratamento.schemas import ItemIn


def test_faces_normalized_in_canonical_order():
    assert normalize_faces("o, m d", 36) == "MDO"
    assert normalize_faces("iP", 11) == "OL"  # incisal e palatina viram O e L
    assert normalize_faces("  ", 36) is None and normalize_faces(None, None) is None
    with pytest.raises(PlanRuleError):
        normalize_faces("O", None)
    with pytest.raises(ValueError):
        normalize_faces("X", 36)


def test_item_schema():
    assert ItemIn(procedure_code="REST", tooth=36, faces="dom").faces == "MDO"
    for bad in ({"tooth": 19}, {"faces": "O"}, {"tooth": 36, "faces": "Z"}):
        with pytest.raises(ValidationError):
            ItemIn(procedure_code="REST", **bad)


def test_discount_limit():
    check_discount(Decimal("5"), Decimal("5"))
    check_discount(Decimal("40"), None)  # admin/gestor
    for pct, limit in (
        (Decimal("5.01"), Decimal("5")),
        (Decimal("101"), None),
        (Decimal("-1"), None),
    ):
        with pytest.raises(PlanRuleError):
            check_discount(pct, limit)


def test_totals_with_partial_approval_and_discount():
    items = [
        (I.APROVADO, Decimal("200.00")),
        (I.REALIZADO, Decimal("120.00")),
        (I.RECUSADO, Decimal("1000.00")),
        (I.CANCELADO, Decimal("50.00")),
        (I.PROPOSTO, None),
    ]
    t = totals(items, Decimal("10"))
    assert t.proposed == Decimal("1370.00")
    assert t.approved_subtotal == Decimal("320.00")
    assert t.discount == Decimal("32.00") and t.approved_total == Decimal("288.00")
    assert totals([(I.APROVADO, Decimal("0.05"))], Decimal("50")).discount == Decimal("0.03")


def test_status_helpers():
    assert is_expired(P.EMITIDO, date(2026, 1, 10), date(2026, 1, 11))
    assert not is_expired(P.EMITIDO, date(2026, 1, 10), date(2026, 1, 10))
    assert not is_expired(P.APROVADO, date(2026, 1, 10), date(2026, 2, 1))
    assert plan_after_decision(0) is P.RECUSADO and plan_after_decision(2) is P.APROVADO
    assert plan_after_items([I.REALIZADO, I.CANCELADO, I.RECUSADO]) is P.CONCLUIDO
    assert plan_after_items([I.REALIZADO, I.APROVADO]) is None
    assert plan_after_items([I.CANCELADO, I.RECUSADO]) is P.CANCELADO
