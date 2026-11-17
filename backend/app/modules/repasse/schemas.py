import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.repasse.models import RuleKind


class RuleIn(BaseModel):
    dentist_id: uuid.UUID
    procedure_code: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None
    ) = Field(None, description="Vazio: regra geral do dentista.")
    kind: RuleKind = RuleKind.PERCENTUAL
    value: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] = Field(
        description="Percentual (0–100) ou valor fixo em R$ por procedimento."
    )
    deduct_materials: bool = False
    deduct_card_fee: bool = False
    valid_from: date | None = Field(None, description="Padrão: hoje.")


class RuleOut(RuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    valid_from: date
    created_at: datetime


class CloseIn(BaseModel):
    dentist_id: uuid.UUID
    period_end: date
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class LineOut(BaseModel):
    plan_item_id: uuid.UUID
    procedure_code: str
    base_amount: Decimal = Field(description="Recebido do plano, rateado para o item.")
    fee_deduction: Decimal
    material_deduction: Decimal
    rule_id: uuid.UUID
    commission: Decimal


class PreviewOut(BaseModel):
    dentist_id: uuid.UUID
    period_start: date | None
    period_end: date
    total: Decimal
    lines: list[LineOut]
    missing_rule: list[str] = Field(description="Procedimentos realizados sem regra de repasse.")


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dentist_id: uuid.UUID
    period_start: date | None
    period_end: date
    total: Decimal
    notes: str | None
    closed_by: uuid.UUID | None
    closed_at: datetime


class SettlementDetail(SettlementOut):
    lines: list[LineOut]
