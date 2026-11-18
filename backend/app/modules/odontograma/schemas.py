import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.odontograma import regras
from app.modules.odontograma.models import (
    Dentition,
    Display3D,
    EventAction,
    StatusKind,
    StatusRegion,
    StatusScope,
)


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
    display_3d: Display3D = Field(
        Display3D.COLORIR, description="No 3D: colorir, ou ocultar o dente (só dente inteiro)."
    )
    region: StatusRegion = Field(
        StatusRegion.COROA, description="Onde pinta: coroa, ou raiz (só dente inteiro; ex.: canal)."
    )


class StatusUpdate(BaseModel):
    name: Name | None = None
    color: Color | None = None
    kind: StatusKind | None = Field(None, description="Só enquanto o item não foi usado.")
    scope: StatusScope | None = Field(None, description="Só enquanto o item não foi usado.")
    sort_order: int | None = Field(None, ge=0, le=10_000)
    display_3d: Display3D | None = None
    region: StatusRegion | None = None
    active: bool | None = None


class StatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    color: str = Field(
        description="Cor que esta pessoa vê: a pessoal, se houver; senão, a da clínica."
    )
    clinic_color: str | None = Field(
        None, description="Cor da clínica (na listagem e na visualização)."
    )
    personal: bool = Field(False, description="`color` é a cor pessoal de quem pediu.")
    kind: StatusKind
    scope: StatusScope
    sort_order: int
    display_3d: Display3D
    region: StatusRegion
    active: bool


class PersonalColorIn(BaseModel):
    color: Color


class ToothNoteIn(BaseModel):
    tooth: Tooth
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ToothNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    tooth: int
    text: str
    created_by: uuid.UUID | None
    created_at: datetime


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
    region: StatusRegion = StatusRegion.COROA


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


# ---------- biblioteca 3D ----------


class PlacementOut(BaseModel):
    translation: list[float] = Field(description="Posição do colo na arcada (mm).")
    rotation: list[float] = Field(description="Quatérnio x, y, z, w (glTF).")
    mesial_x: int = Field(description="+1: mesial em +X no dente isolado; -1: em -X.")


class LibraryToothOut(BaseModel):
    fdi: int
    deciduous: bool
    kind: str = Field(description="incisivo, canino, pre_molar ou molar.")
    nodes: list[str]
    face_labels: dict[str, str]
    placement: PlacementOut = Field(description="Na arcada permanente ou mista.")
    placement_deciduous_arch: PlacementOut | None = Field(
        None, description="Na arcada só de decíduos (menor)."
    )


class LibraryOut(BaseModel):
    version: str
    units: str
    conventions: dict[str, str]
    teeth: list[LibraryToothOut]


# ---------- visualização 2D/3D ----------


class FaceViewOut(BaseModel):
    face: str = Field(description="Face gravada (M, D, O, V, L).")
    node: str = Field(description="Nó da malha no .glb (ex.: 11_V).")
    color: str | None = Field(description="Cor a pintar; null = cor natural do dente.")
    marks: list[MarkOut] = Field(description="Marcações da face, da mais importante à menor.")


class ToothViewOut(BaseModel):
    tooth: int
    deciduous: bool
    in_arch: bool = Field(description="false: marcado, mas fora da arcada do paciente.")
    hidden: bool = Field(description="Ocultar no 3D (item de dente inteiro com `ocultar`).")
    node: str = Field(description="Nó do dente no .glb (ex.: dente_11).")
    color: str | None = Field(
        description="Cor do item mais importante da coroa (itens de dente inteiro da coroa)."
    )
    root_color: str | None = Field(
        description="Cor do item mais importante da raiz (canal, lesão periapical...)."
    )
    whole: list[MarkOut]
    faces: dict[str, FaceViewOut] = Field(description="As cinco faces, pelo rótulo clínico.")
    placement: PlacementOut = Field(description="Posição na arcada deste paciente.")


class VisualizationOut(BaseModel):
    patient_id: uuid.UUID
    at: datetime
    arch: ArchOut
    library_version: str
    arch_model_url: str = Field(description="GLB da arcada do paciente (sem dado pessoal).")
    teeth: list[ToothViewOut] = Field(description="Na ordem de leitura do odontograma.")
    legend: list[StatusOut] = Field(description="Itens da legenda presentes nas marcações.")


class ChangeOut(BaseModel):
    tooth: int
    face: str | None
    face_label: str | None
    mark: MarkOut


class ComparisonOut(BaseModel):
    patient_id: uuid.UUID
    since: datetime
    until: datetime
    added: list[ChangeOut] = Field(description="Marcações que entraram no período.")
    removed: list[ChangeOut] = Field(description="Marcações que saíram no período.")
    teeth_changed: list[int]
