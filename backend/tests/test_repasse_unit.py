"""Repasse: escolha da regra, fração paga e linha acumulada (sem banco)."""

from datetime import date
from decimal import Decimal

from app.modules.repasse.regras import Rule, compute_line, paid_ratio, pick_rule

D = Decimal


def _rule(code=None, kind="percentual", value="40", since=date(2026, 1, 1), fee=False, mat=False):
    return Rule(object(), code, kind, D(value), mat, fee, since)


def test_pick_rule_prefers_procedure_then_latest_valid():
    general_old = _rule(value="30", since=date(2026, 1, 1))
    general_new = _rule(value="40", since=date(2026, 6, 1))
    implant = _rule(code="IMPLANTE", value="25", since=date(2026, 3, 1))
    rules = [general_old, general_new, implant]
    assert pick_rule(rules, "RESTAURACAO", date(2026, 5, 1)) is general_old
    assert pick_rule(rules, "RESTAURACAO", date(2026, 7, 1)) is general_new
    assert pick_rule(rules, "IMPLANTE", date(2026, 7, 1)) is implant
    assert pick_rule(rules, "IMPLANTE", date(2026, 2, 1)) is general_old  # exceção ainda não vigia
    assert pick_rule(rules, "X", date(2025, 12, 31)) is None


def test_paid_ratio_bounds():
    assert paid_ratio(D("160"), D("320")) == D("0.5")
    assert paid_ratio(D("400"), D("320")) == 1
    assert paid_ratio(D("-10"), D("320")) == 0
    assert paid_ratio(D("10"), D("0")) == 0


def test_percentual_line_with_fee_and_materials():
    line = compute_line(item_net=D("200"), ratio=D("0.5"), already_based=D("0"),
                        fee_ratio=D("0.05"), material_cost=D("30"),
                        rule=_rule(fee=True, mat=True))  # fmt: skip
    assert line.base == D("100.00") and line.fee_deduction == D("5.00")
    assert line.material_deduction == D("15.00")
    assert line.commission == D("32.00")  # (100 − 5 − 15) × 40%


def test_cumulative_and_clawback():
    rule = _rule()
    second = compute_line(item_net=D("200"), ratio=D("1"), already_based=D("100"),
                          fee_ratio=D("0"), material_cost=D("0"), rule=rule)  # fmt: skip
    assert second.base == D("100.00") and second.commission == D("40.00")
    back = compute_line(item_net=D("200"), ratio=D("0.25"), already_based=D("100"),
                        fee_ratio=D("0"), material_cost=D("0"), rule=rule)  # fmt: skip
    assert back.base == D("-50.00") and back.commission == D("-20.00")  # estorno depois


def test_fixed_rule_is_proportional_and_without_deductions():
    rule = _rule(kind="fixo", value="50", fee=True, mat=True)
    line = compute_line(item_net=D("120"), ratio=D("0.5"), already_based=D("0"),
                        fee_ratio=D("0.1"), material_cost=D("20"), rule=rule)  # fmt: skip
    assert (line.base, line.fee_deduction, line.material_deduction, line.commission) == (
        D("60.00"), D("0.00"), D("0.00"), D("25.00"),
    )  # fmt: skip
