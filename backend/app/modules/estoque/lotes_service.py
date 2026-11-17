"""Lotes, movimentos e baixa automática. O commit e a auditoria ficam com o router.

Interface para outros módulos: `consume_for_procedure` (usada pelo tratamento ao realizar
um item do plano).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.modules.estoque import regras
from app.modules.estoque.models import Material, MovementKind, StockLot, StockMovement
from app.modules.estoque.service import NotFound, RuleViolation, get_material

MAX_LIST = 500


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def _balances(db: Session, lot_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not lot_ids:
        return {}
    rows = db.execute(
        select(StockMovement.lot_id, func.sum(StockMovement.quantity))
        .where(StockMovement.lot_id.in_(lot_ids))
        .group_by(StockMovement.lot_id)
    )
    return {lot_id: regras.qty(total) for lot_id, total in rows.all()}


def lot_balances(
    db: Session, material_id: uuid.UUID, *, lock: bool = False
) -> list[tuple[StockLot, Decimal]]:
    query = select(StockLot).where(StockLot.material_id == material_id)
    if lock:
        query = query.with_for_update()
    lots = list(db.scalars(query.order_by(StockLot.expires_on, StockLot.received_on)))
    balances = _balances(db, [lot.id for lot in lots])
    return [(lot, balances.get(lot.id, regras.qty(Decimal("0")))) for lot in lots]


def _as_rule(lots: list[tuple[StockLot, Decimal]]) -> list[regras.LotBalance]:
    return [
        regras.LotBalance(lot.id, bal, lot.expires_on, lot.received_on, lot.unit_cost)
        for lot, bal in lots
    ]


def _movement(db, user, lot: StockLot, kind: MovementKind, quantity: Decimal, **extra):
    movement = StockMovement(
        clinic_id=user.clinic_id,
        lot_id=lot.id,
        material_id=lot.material_id,
        kind=kind,
        quantity=regras.qty(quantity),
        recorded_by=user.user_id,
        **extra,
    )
    db.add(movement)
    return movement


def get_lot(db: Session, lot_id: uuid.UUID) -> StockLot:
    lot = db.scalar(select(StockLot).where(StockLot.id == lot_id).with_for_update())
    if lot is None:
        raise NotFound("Lote não encontrado.")
    return lot


def lot_balance(db: Session, lot: StockLot) -> Decimal:
    return _balances(db, [lot.id]).get(lot.id, regras.qty(Decimal("0")))


def register_entry(db: Session, user: CurrentUser, data: dict, *, can_set_cost: bool) -> StockLot:
    """Entrada de compra: cria o lote e atualiza o custo médio do material.

    Quem não vê custo (ASB) não informa custo: o lote entra pelo custo atual do material,
    e o custo médio não muda por causa dele.
    """
    material = get_material(db, data["material_id"])
    if can_set_cost and data.get("unit_cost") is None:
        raise RuleViolation("Informe o custo unitário da compra.")
    if not can_set_cost and data.get("unit_cost") is not None:
        raise RuleViolation("Só administrador e gestor informam o custo da compra.")
    cost = data["unit_cost"] if can_set_cost else material.unit_cost
    if not material.active:
        raise RuleViolation("Material desativado: reative antes de dar entrada.")
    received = data.get("received_on") or today()
    if received > today():
        raise RuleViolation("A data de recebimento não pode ser futura.")
    lot = StockLot(
        clinic_id=user.clinic_id,
        material_id=material.id,
        lot_code=data.get("lot_code"),
        expires_on=data.get("expires_on"),
        unit_cost=regras.qty(cost),
        received_on=received,
        supplier=data.get("supplier"),
        created_by=user.user_id,
    )
    db.add(lot)
    db.flush()
    _movement(db, user, lot, MovementKind.ENTRADA, data["quantity"])
    db.flush()
    # Custo médio ponderado do que está em estoque (a precificação usa este valor). Só
    # recalcula quando a entrada trouxe custo informado (admin/gestor).
    if can_set_cost:
        db.execute(select(Material.id).where(Material.id == material.id).with_for_update())
        average = regras.weighted_cost(_as_rule(lot_balances(db, material.id)))
        if average is not None:
            material.unit_cost = average
    db.flush()
    return lot


def register_exit(db: Session, user: CurrentUser, lot: StockLot, quantity: Decimal, reason: str):
    """Saída manual (perda, vencido, uso fora de procedimento). O lote deve vir travado."""
    if quantity > lot_balance(db, lot):
        raise RuleViolation("Quantidade acima do saldo do lote.")
    movement = _movement(db, user, lot, MovementKind.SAIDA, -quantity, reason=reason)
    db.flush()
    return movement


def register_adjustment(
    db: Session, user: CurrentUser, lot: StockLot, counted: Decimal, reason: str
) -> StockMovement | None:
    """Ajuste de inventário para a quantidade contada. None se já bate."""
    delta = regras.qty(counted) - lot_balance(db, lot)
    if delta == 0:
        return None
    movement = _movement(db, user, lot, MovementKind.AJUSTE, delta, reason=reason)
    db.flush()
    return movement


@dataclass
class Shortage:
    material_id: uuid.UUID
    material_name: str
    missing: Decimal


def consume_for_procedure(
    db: Session,
    user: CurrentUser,
    *,
    procedure_code: str,
    patient_id: uuid.UUID,
    plan_item_id: uuid.UUID,
) -> tuple[list[StockMovement], list[Shortage]]:
    """Baixa os materiais da ficha técnica do procedimento (FEFO, sem lotes vencidos).

    Falta de estoque não impede o procedimento: baixa o que houver e devolve o que faltou.
    Sem ficha técnica, não baixa nada.
    """
    # Import local: a ficha técnica é da precificação, que já depende do estoque.
    from app.modules.precificacao.models import CostSheet, CostSheetItem

    sheet = db.scalar(select(CostSheet).where(CostSheet.procedure_code == procedure_code))
    if sheet is None:
        return [], []
    items = db.execute(
        select(CostSheetItem, Material)
        .join(Material, Material.id == CostSheetItem.material_id)
        .where(CostSheetItem.sheet_id == sheet.id)
        .order_by(Material.name)
    ).all()
    day = today()
    movements: list[StockMovement] = []
    shortages: list[Shortage] = []
    for item, material in items:
        lots = lot_balances(db, material.id, lock=True)
        by_id = {lot.id: lot for lot, _ in lots}
        taken, missing = regras.allocate(_as_rule(lots), item.quantity, day)
        for lot_id, part in taken:
            movements.append(
                _movement(
                    db,
                    user,
                    by_id[lot_id],
                    MovementKind.CONSUMO,
                    -part,
                    patient_id=patient_id,
                    plan_item_id=plan_item_id,
                    reason=f"Procedimento {procedure_code}",
                )  # fmt: skip
            )
        if missing > 0:
            shortages.append(Shortage(material.id, material.name, missing))
    db.flush()
    return movements, shortages


# ---------- consultas ----------


@dataclass
class MaterialStock:
    material: Material
    lots: list[tuple[StockLot, Decimal]]

    @property
    def balance(self) -> Decimal:
        return regras.qty(sum((b for _, b in self.lots), Decimal("0")))

    @property
    def below_minimum(self) -> bool:
        m = self.material.min_quantity
        return m is not None and self.balance < m


def stock(db: Session, *, include_inactive: bool = False) -> list[MaterialStock]:
    query = select(Material).order_by(Material.name)
    if not include_inactive:
        query = query.where(Material.active.is_(True))
    materials = list(db.scalars(query))
    lots = list(
        db.scalars(
            select(StockLot)
            .where(StockLot.material_id.in_([m.id for m in materials]))
            .order_by(StockLot.expires_on, StockLot.received_on)
        )
    )
    balances = _balances(db, [lot.id for lot in lots])
    by_material: dict[uuid.UUID, list[tuple[StockLot, Decimal]]] = {m.id: [] for m in materials}
    for lot in lots:
        by_material[lot.material_id].append((lot, balances.get(lot.id, regras.qty(Decimal("0")))))
    return [MaterialStock(m, by_material[m.id]) for m in materials]


def movements(
    db: Session,
    *,
    material_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[StockMovement]:
    query = select(StockMovement).order_by(StockMovement.created_at.desc())
    if material_id is not None:
        query = query.where(StockMovement.material_id == material_id)
    if lot_id is not None:
        query = query.where(StockMovement.lot_id == lot_id)
    return list(db.scalars(query.limit(min(limit, MAX_LIST))))


def patient_trace(db: Session, patient_id: uuid.UUID):
    """O que foi usado no paciente, com lote e validade (rastreabilidade)."""
    query = (
        select(StockMovement, Material.name, StockLot.lot_code, StockLot.expires_on)
        .join(Material, Material.id == StockMovement.material_id)
        .join(StockLot, StockLot.id == StockMovement.lot_id)
        .where(StockMovement.patient_id == patient_id)
        .order_by(StockMovement.created_at.desc())
    )
    return db.execute(query).all()
