import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.imagens.models import ImageKind


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    kind: ImageKind
    teeth: list[int] | None
    exam_date: date | None = Field(description="Data do exame (padrão: a do DICOM).")
    notes: str | None
    file_name: str
    size_bytes: int
    sha256: str
    modality: str | None = Field(description="Modalidade DICOM (PX, IO, CT...).")
    study_date: date | None
    study_description: str | None
    series_description: str | None
    body_part: str | None
    manufacturer: str | None
    rows: int | None
    columns: int | None
    dicom_patient_name: str | None = Field(
        description="Nome do paciente gravado no arquivo, para conferir o envio."
    )
    uploaded_by: uuid.UUID | None
    created_at: datetime
    invalidated_at: datetime | None
    invalidation_reason: str | None


class ExamDetail(ExamOut):
    study_uid: str | None
    series_uid: str | None
    sop_uid: str | None
    dicom_metadata: dict[str, Any] = Field(description="Tags DICOM selecionadas.")


class ExamUpdate(BaseModel):
    """Só os campos enviados mudam (o arquivo e os metadados não mudam)."""

    kind: ImageKind | None = None
    teeth: list[int] | None = Field(None, max_length=52)
    exam_date: date | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class InvalidateIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
