import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from app.modules.agenda.models import AppointmentStatus, EntryKind, EventAction


def _text(max_length: int):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)
    ]


class ChairCreate(BaseModel):
    name: _text(80)


class ChairUpdate(BaseModel):
    name: _text(80) | None = None
    active: bool | None = None


class ChairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    active: bool


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    dentist_id: uuid.UUID
    chair_id: uuid.UUID | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    procedure: _text(200) | None = None
    notes: _text(1000) | None = None


class BlockCreate(BaseModel):
    dentist_id: uuid.UUID | None = None
    chair_id: uuid.UUID | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    notes: _text(1000) | None = None


class EntryUpdate(BaseModel):
    """Só os campos enviados mudam. Horário, dentista e cadeira = remarcação."""

    dentist_id: uuid.UUID | None = None
    chair_id: uuid.UUID | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    procedure: _text(200) | None = None
    notes: _text(1000) | None = None


class StatusChange(BaseModel):
    status: AppointmentStatus
    motivo: _text(300) | None = None


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: EntryKind
    status: AppointmentStatus
    patient_id: uuid.UUID | None
    patient_name: str | None = None
    dentist_id: uuid.UUID | None
    chair_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    procedure: str | None
    notes: str | None
    status_reason: str | None
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: EventAction
    status: AppointmentStatus
    details: dict[str, Any] | None
    user_id: uuid.UUID | None
    created_at: datetime


class EntryDetail(EntryOut):
    historico: list[EventOut]
