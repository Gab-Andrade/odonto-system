import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.tratamento import regras
from app.modules.tratamento.models import ItemStatus, PlanStatus


def _text(max_length: int):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)
    ]


Pct = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class SettingsIn(BaseModel):
    validity_days: int = Field(ge=1, le=365)
    max_discount_pct: Pct


class SettingsOut(SettingsIn):
    pass


class ItemIn(BaseModel):
    procedure_code: _text(40)
    tooth: int | None = None
    faces: str | None = Field(None, max_length=20, description='Ex.: "MOD" ou "O, V".')
    notes: _text(500) | None = None
    planned_status_id: uuid.UUID | None = Field(
        None, description="Item da legenda do odontograma que indica o 'a fazer'."
    )
    done_status_id: uuid.UUID | None = Field(
        None, description="Item da legenda marcado no odontograma ao realizar."
    )
    sort_order: int | None = Field(
        None, ge=0, le=100_000, description="Padrão: depois do último item."
    )

    @model_validator(mode="after")
    def _tooth_faces(self):
        regras.check_tooth(self.tooth)
        self.faces = regras.normalize_faces(self.faces, self.tooth)
        return self


class ItemUpdate(ItemIn):
    """Substitui o item inteiro (só no rascunho)."""


class PlanCreate(BaseModel):
    patient_id: uuid.UUID
    dentist_id: uuid.UUID | None = Field(
        None, description="Responsável (padrão: quem cria, se for dentista ou admin)."
    )
    title: _text(120) | None = None
    notes: _text(2000) | None = None
    items: list[ItemIn] = Field(default_factory=list, max_length=200)


class PlanUpdate(BaseModel):
    dentist_id: uuid.UUID | None = None
    title: _text(120) | None = None
    notes: _text(2000) | None = None


class DiscountIn(BaseModel):
    discount_pct: Pct


class DecisionIn(BaseModel):
    approved_item_ids: list[uuid.UUID] = Field(
        description="Itens aprovados pelo paciente; os demais ficam recusados.", max_length=200
    )


class ReasonIn(BaseModel):
    reason: _text(300)


class PerformIn(BaseModel):
    encounter_id: uuid.UUID = Field(description="Atendimento aberto em que foi realizado.")


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    sort_order: int
    procedure_code: str
    description: str | None
    tooth: int | None
    faces: str | None
    notes: str | None
    planned_status_id: uuid.UUID | None
    done_status_id: uuid.UUID | None
    status: ItemStatus
    unit_price: Decimal | None = Field(description="Congelado na emissão.")
    price_snapshot_id: uuid.UUID | None
    estimated_price: Decimal | None = Field(
        None, description="Só no rascunho: preço que seria congelado se emitisse agora."
    )
    estimate_error: str | None = None
    encounter_id: uuid.UUID | None
    performed_by: uuid.UUID | None
    performed_at: datetime | None
    cancel_reason: str | None


class TotalsOut(BaseModel):
    proposed: Decimal
    approved_subtotal: Decimal
    discount: Decimal
    approved_total: Decimal


class PlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    dentist_id: uuid.UUID
    status: PlanStatus
    expired: bool = False
    title: str | None
    discount_pct: Decimal
    valid_until: date | None
    issued_at: datetime | None
    decided_at: datetime | None
    created_at: datetime


class PlanOut(PlanSummary):
    notes: str | None
    issued_by: uuid.UUID | None
    decided_by: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_by: uuid.UUID | None
    items: list[ItemOut]
    totals: TotalsOut
