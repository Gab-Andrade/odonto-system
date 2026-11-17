import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.modules.estoque.models import Material

COST_PLACES = Decimal("0.0001")


def _cost(value: Decimal) -> Decimal:
    """Custo sempre com 4 casas, igual ao que o banco guarda (Numeric(12, 4))."""
    return Decimal(value).quantize(COST_PLACES)


class StockError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(StockError):
    pass


class RuleViolation(StockError):
    pass


def list_materials(db: Session, *, include_inactive: bool = False) -> list[Material]:
    stmt = select(Material).order_by(Material.name)
    if not include_inactive:
        stmt = stmt.where(Material.active)
    return list(db.scalars(stmt))


def get_material(db: Session, material_id: uuid.UUID) -> Material:
    material = db.get(Material, material_id)  # o RLS esconde materiais de outras clínicas
    if material is None:
        raise NotFound("Material não encontrado.")
    return material


def _ensure_unique_name(db: Session, name: str, exclude_id: uuid.UUID | None = None) -> None:
    stmt = select(Material.id).where(func.lower(Material.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(Material.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise RuleViolation(f"Já existe um material chamado '{name}'.")


def create_material(
    db: Session,
    user: CurrentUser,
    *,
    name: str,
    unit: str,
    category: str | None,
    unit_cost: Decimal,
) -> Material:
    _ensure_unique_name(db, name)
    material = Material(
        clinic_id=user.clinic_id,
        name=name,
        unit=unit,
        category=category,
        unit_cost=_cost(unit_cost),
    )
    db.add(material)
    db.flush()
    return material


def update_material(db: Session, material: Material, changes: dict[str, Any]) -> Material:
    if changes.get("name") is not None:
        _ensure_unique_name(db, changes["name"], exclude_id=material.id)
        material.name = changes["name"]
    if changes.get("unit") is not None:
        material.unit = changes["unit"]
    if "category" in changes:
        material.category = changes["category"]
    if changes.get("unit_cost") is not None:
        material.unit_cost = _cost(changes["unit_cost"])
    if changes.get("active") is not None:
        material.active = changes["active"]
    db.flush()
    return material


# ---------- Interface para outros módulos ----------


@dataclass(frozen=True)
class MaterialCost:
    id: uuid.UUID
    name: str
    unit: str
    unit_cost: Decimal
    active: bool


def material_costs(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, MaterialCost]:
    """Custo unitário atual dos materiais pedidos (só os da clínica da sessão; os demais
    simplesmente não aparecem no resultado)."""
    wanted = set(ids)
    if not wanted:
        return {}
    rows = db.scalars(select(Material).where(Material.id.in_(wanted)))
    return {m.id: MaterialCost(m.id, m.name, m.unit, m.unit_cost, m.active) for m in rows}
