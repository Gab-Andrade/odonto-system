"""Regras puras do plano de tratamento e orçamento (testáveis sem banco)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.modules.odontograma import regras as odonto
from app.modules.tratamento.models import ItemStatus, PlanStatus

CENT = Decimal("0.01")
COUNTED = (ItemStatus.APROVADO, ItemStatus.REALIZADO)  # entram no total aprovado


class PlanRuleError(ValueError):
    pass


def normalize_faces(faces: str | None, tooth: int | None) -> str | None:
    """'o, m d' → 'MDO' (ordem M, D, O, V, L; sem repetir). Exige dente."""
    if faces is None:
        return None
    letters = [c for c in faces.upper() if not c.isspace() and c != ","]
    if not letters:
        return None
    if tooth is None:
        raise PlanRuleError("Faces só com o dente informado.")
    codes = {odonto.normalize_face(c) for c in letters}
    return "".join(f for f in odonto.FACES if f in codes)


def check_tooth(tooth: int | None) -> None:
    if tooth is not None and not odonto.is_valid_tooth(tooth):
        raise PlanRuleError("Dente inválido na numeração FDI (11–48, 51–85).")


def check_discount(pct: Decimal, limit: Decimal | None) -> None:
    """`limit` None = sem limite (admin e gestor)."""
    if pct < 0 or pct > 100:
        raise PlanRuleError("Desconto entre 0% e 100%.")
    if limit is not None and pct > limit:
        raise PlanRuleError(f"Desconto acima de {limit}% precisa de administrador ou gestor.")


def is_expired(status: PlanStatus, valid_until: date | None, today: date) -> bool:
    return status is PlanStatus.EMITIDO and valid_until is not None and today > valid_until


@dataclass(frozen=True)
class Totals:
    proposed: Decimal  # soma de todos os itens com preço
    approved_subtotal: Decimal  # aprovados + realizados
    discount: Decimal
    approved_total: Decimal


def totals(items: Iterable[tuple[ItemStatus, Decimal | None]], discount_pct: Decimal) -> Totals:
    proposed = Decimal("0")
    approved = Decimal("0")
    for status, price in items:
        if price is None:
            continue
        proposed += price
        if status in COUNTED:
            approved += price
    discount = (approved * discount_pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return Totals(
        proposed=proposed.quantize(CENT),
        approved_subtotal=approved.quantize(CENT),
        discount=discount,
        approved_total=(approved - discount).quantize(CENT),
    )


def plan_after_decision(approved_count: int) -> PlanStatus:
    return PlanStatus.APROVADO if approved_count > 0 else PlanStatus.RECUSADO


def plan_after_items(item_statuses: Iterable[ItemStatus]) -> PlanStatus | None:
    """Status do plano aprovado quando nada aprovado ficou por fazer: concluído se algo foi
    realizado, cancelado se tudo foi cancelado. None = ainda há itens a fazer."""
    statuses = list(item_statuses)
    if ItemStatus.APROVADO in statuses:
        return None
    return PlanStatus.CONCLUIDO if ItemStatus.REALIZADO in statuses else PlanStatus.CANCELADO
