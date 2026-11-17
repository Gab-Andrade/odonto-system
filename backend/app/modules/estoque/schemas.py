import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=4)]


class MaterialCreate(BaseModel):
    name: Name
    unit: Unit = Field(description="Unidade de uso: un, ml, g, cx, par, tubo...")
    category: str | None = Field(default=None, max_length=100)
    unit_cost: UnitCost = Field(description="Custo por unidade de uso, até 4 casas decimais.")


class MaterialUpdate(BaseModel):
    name: Name | None = None
    unit: Unit | None = None
    category: str | None = Field(default=None, max_length=100)
    unit_cost: UnitCost | None = None
    active: bool | None = None


class MaterialOut(BaseModel):
    """Visão sem custo (dentista e ASB)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    category: str | None
    active: bool


class MaterialCostOut(MaterialOut):
    """Visão com custo (admin e gestor)."""

    unit_cost: Decimal
    updated_at: datetime
