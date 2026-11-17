import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=4)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=4)]
MinQuantity = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=4)]


def _text(max_length: int):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)
    ]


class MaterialCreate(BaseModel):
    name: Name
    unit: Unit = Field(description="Unidade de uso: un, ml, g, cx, par, tubo...")
    category: str | None = Field(default=None, max_length=100)
    unit_cost: UnitCost = Field(description="Custo por unidade de uso, até 4 casas decimais.")
    min_quantity: MinQuantity | None = Field(None, description="Estoque mínimo (alerta).")


class MaterialUpdate(BaseModel):
    name: Name | None = None
    unit: Unit | None = None
    category: str | None = Field(default=None, max_length=100)
    unit_cost: UnitCost | None = None
    min_quantity: MinQuantity | None = None
    active: bool | None = None


class MaterialOut(BaseModel):
    """Visão sem custo (dentista e ASB)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    category: str | None
    min_quantity: Decimal | None
    active: bool


class MaterialCostOut(MaterialOut):
    """Visão com custo (admin e gestor)."""

    unit_cost: Decimal
    updated_at: datetime


# ---------- lotes e movimentos ----------


class EntryIn(BaseModel):
    material_id: uuid.UUID
    quantity: Quantity
    unit_cost: UnitCost | None = Field(
        None,
        description="Custo por unidade nesta compra. Obrigatório para admin e gestor;"
        " a ASB não informa (o lote usa o custo atual do material).",
    )
    lot_code: _text(60) | None = None
    expires_on: date | None = None
    supplier: _text(150) | None = None
    received_on: date | None = Field(None, description="Padrão: hoje.")


class ExitIn(BaseModel):
    lot_id: uuid.UUID
    quantity: Quantity
    reason: _text(300) = Field(description="Ex.: perda, vencido, uso fora de procedimento.")


class AdjustIn(BaseModel):
    lot_id: uuid.UUID
    counted_quantity: MinQuantity = Field(description="Quantidade contada no inventário.")
    reason: _text(300)


class LotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    lot_code: str | None
    expires_on: date | None
    received_on: date
    supplier: str | None
    balance: Decimal = Decimal("0")
    expiry: str = "ok"
    unit_cost: Decimal | None = Field(None, description="Só para admin e gestor.")


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    material_id: uuid.UUID
    kind: str
    quantity: Decimal
    reason: str | None
    patient_id: uuid.UUID | None
    plan_item_id: uuid.UUID | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class StockOut(BaseModel):
    material_id: uuid.UUID
    name: str
    unit: str
    balance: Decimal
    min_quantity: Decimal | None
    below_minimum: bool
    lots: list[LotOut]


class TraceOut(MovementOut):
    material_name: str
    lot_code: str | None
    expires_on: date | None
