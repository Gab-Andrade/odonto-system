import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.odontograma import regras
from app.modules.odontograma.models import Dentition, EventAction, StatusKind, StatusScope


def _tooth(value: int) -> int:
    if not regras.is_valid_tooth(value):
        raise ValueError("Dente inválido na numeração FDI (11–48, 51–85).")
    return value


def _face(value: str | None) -> str | None:
    return regras.normalize_face(value)


Tooth = Annotated[int, AfterValidator(_tooth)]
Face = Annotated[str | None, AfterValidator(_face)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]
Color = Annotated[str, StringConstraints(to_upper=True, pattern=r"^#[0-9A-Fa-f]{6}$")]


class StatusCreate(BaseModel):
    code: Code
    name: Name
    color: Color
    kind: StatusKind
    scope: StatusScope
    sort_order: int = Field(0, ge=0, le=10_000)


class StatusUpdate(BaseModel):
    name: Name | None = None
    color: Color | None = None
    kind: StatusKind | None = Field(None, description="Só enquanto o item não foi usado.")
    scope: StatusScope | None = Field(None, description="Só enquanto o item não foi usado.")
    sort_order: int | None = Field(None, ge=0, le=10_000)
    active: bool | None = None


class StatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    color: str
    kind: StatusKind
    scope: StatusScope
    sort_order: int
    active: bool


class EventIn(BaseModel):
    tooth: Tooth
    face: Face = Field(None, description="M, D, O/I, V ou L/P; vazio para item de dente inteiro.")
    status_id: uuid.UUID
    action: EventAction = EventAction.MARCAR
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class EventsIn(BaseModel):
    encounter_id: uuid.UUID | None = Field(None, description="Atendimento aberto do paciente.")
    events: list[EventIn] = Field(min_length=1, max_length=200)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    tooth: int
    face: str | None
    face_label: str | None = None
    status_id: uuid.UUID
    action: EventAction
    encounter_id: uuid.UUID | None
    notes: str | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class MarkOut(BaseModel):
    status_id: uuid.UUID
    code: str
    name: str
    color: str
    kind: StatusKind


class ToothOut(BaseModel):
    tooth: int
    deciduous: bool
    whole: list[MarkOut] = Field(description="Marcações do dente inteiro.")
    faces: dict[str, list[MarkOut]] = Field(description="Por face, com o rótulo clínico.")


class OdontogramOut(BaseModel):
    patient_id: uuid.UUID
    at: datetime = Field(description="Momento a que o odontograma se refere.")
    teeth: list[ToothOut] = Field(description="Só dentes com alguma marcação.")


# ---------- arcada ----------

ThirdMolar = Literal[18, 28, 38, 48]


class ArchIn(BaseModel):
    dentition: Dentition
    third_molars: list[ThirdMolar] | None = Field(
        None,
        description=(
            "Só na permanente, sem `teeth`. Omitido na permanente: os quatro (32 dentes)."
        ),
    )
    teeth: list[Tooth] | None = Field(
        None,
        max_length=52,
        description="Composição explícita (ex.: mista fora do padrão). Sem ela, usa o padrão.",
    )
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ArchOut(BaseModel):
    patient_id: uuid.UUID
    source: Literal["registrada", "padrao"] = Field(
        description="`padrao`: nada registrado; sugerida pela idade do paciente."
    )
    dentition: Dentition
    teeth: list[int] = Field(description="Na ordem de leitura: 18→11, 21→28, 48→41, 31→38.")
    third_molars: list[int]
    id: uuid.UUID | None = None
    notes: str | None = None
    recorded_by: uuid.UUID | None = None
    created_at: datetime | None = None
