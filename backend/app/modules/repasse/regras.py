"""Regras puras do repasse (testáveis sem banco)."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")


class CommissionRuleError(ValueError):
    pass


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Rule:
    key: object  # id da regra
    procedure_code: str | None
    kind: str  # "percentual" | "fixo"
    value: Decimal
    deduct_materials: bool
    deduct_card_fee: bool
    valid_from: date


def pick_rule(rules: list[Rule], procedure_code: str, on: date) -> Rule | None:
    """Regra do procedimento, senão a geral do dentista; a de vigência mais recente até
    `on`."""
    for specific in (True, False):
        candidates = [
            r
            for r in rules
            if r.valid_from <= on
            and ((r.procedure_code == procedure_code) if specific else r.procedure_code is None)
        ]
        if candidates:
            return max(candidates, key=lambda r: r.valid_from)
    return None


def paid_ratio(paid: Decimal, approved_total: Decimal) -> Decimal:
    """Fração do plano já paga (entre 0 e 1)."""
    if approved_total <= 0:
        return ZERO
    return max(ZERO, min(Decimal("1"), paid / approved_total))


@dataclass(frozen=True)
class Line:
    base: Decimal
    fee_deduction: Decimal
    material_deduction: Decimal
    commission: Decimal


def compute_line(
    *,
    item_net: Decimal,
    ratio: Decimal,
    already_based: Decimal,
    fee_ratio: Decimal,
    material_cost: Decimal,
    rule: Rule,
) -> Line:
    """Repasse de um item realizado neste fechamento (diferença do acumulado).

    - base = valor líquido do item (com desconto do plano) × fração paga − já repassado;
    - taxa = base × (taxas ÷ recebido do plano), se a regra desconta taxa;
    - materiais = custo consumido × (base ÷ valor do item), se a regra desconta materiais;
    - comissão = (base − descontos) × %; no valor fixo, valor × (base ÷ valor do item), sem
      descontos.
    """
    earned = money(item_net * ratio)
    base = money(earned - already_based)
    share = (base / item_net) if item_net > 0 else ZERO
    if rule.kind != "percentual":
        # Valor fixo por procedimento: proporcional ao que já foi pago, sem descontos.
        return Line(base, money(ZERO), money(ZERO), money(rule.value * share))
    fee = money(base * fee_ratio) if rule.deduct_card_fee else money(ZERO)
    materials = money(material_cost * share) if rule.deduct_materials else money(ZERO)
    commission = money((base - fee - materials) * rule.value / 100)
    return Line(base, fee, materials, commission)
