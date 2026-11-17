"""Regras puras do financeiro (testáveis sem banco)."""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
MAX_INSTALLMENTS = 48


class FinanceRuleError(ValueError):
    pass


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def add_months(start: date, months: int) -> date:
    """Mesmo dia, `months` meses depois; no fim do mês quando o dia não existe (31 → 30)."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class Installment:
    kind: str  # "entrada" | "parcela"
    number: int | None
    count: int | None
    due_date: date
    amount: Decimal


def split(
    total: Decimal,
    *,
    down_payment: Decimal,
    installments: int,
    down_payment_date: date,
    first_due_date: date,
) -> list[Installment]:
    """Entrada + N parcelas mensais. Os centavos que sobram da divisão vão na 1ª parcela,
    para a soma bater exatamente com o total."""
    total, down_payment = money(total), money(down_payment)
    if total <= 0:
        raise FinanceRuleError("Nada a parcelar: o total aprovado é zero.")
    if down_payment < 0 or down_payment > total:
        raise FinanceRuleError("Entrada entre zero e o total.")
    rest = total - down_payment
    if rest > 0 and not 1 <= installments <= MAX_INSTALLMENTS:
        raise FinanceRuleError(f"Parcelas entre 1 e {MAX_INSTALLMENTS}.")
    if rest == 0 and installments:
        raise FinanceRuleError("Entrada cobre o total: não há parcelas.")
    if rest > 0 and first_due_date < down_payment_date:
        raise FinanceRuleError("A primeira parcela não pode vencer antes da entrada.")

    result = []
    if down_payment > 0:
        result.append(Installment("entrada", None, None, down_payment_date, down_payment))
    if rest > 0:
        base = (rest / installments).quantize(CENT, rounding=ROUND_DOWN)
        if base <= 0:
            raise FinanceRuleError(
                "Parcelas demais para o valor: cada uma ficaria abaixo de R$ 0,01."
            )
        first = rest - base * (installments - 1)
        for n in range(installments):
            result.append(
                Installment(
                    "parcela",
                    n + 1,
                    installments,
                    add_months(first_due_date, n),
                    first if n == 0 else base,
                )
            )
    return result


def fee(amount: Decimal, fee_pct: Decimal) -> tuple[Decimal, Decimal]:
    """(taxa, líquido) de um recebimento."""
    if fee_pct < 0 or fee_pct > 100:
        raise FinanceRuleError("Taxa entre 0% e 100%.")
    value = money(amount * fee_pct / 100)
    return value, money(amount - value)


def receivable_status(
    amount: Decimal, paid: Decimal, due: date, today: date, cancelled: bool
) -> str:
    if cancelled:
        return "cancelada"
    if paid >= amount:
        return "paga"
    if due < today:
        return "vencida"
    return "parcial" if paid > 0 else "aberta"
