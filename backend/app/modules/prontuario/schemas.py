import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.prontuario import anamnese
from app.modules.prontuario.anamnese import QuestionType
from app.modules.prontuario.models import VersionStatus


def _text(max_length: int):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)
    ]


Option = _text(100)


class Question(BaseModel):
    """Uma pergunta do formulário. `id` identifica a resposta e se mantém entre versões."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, StringConstraints(pattern=anamnese.QUESTION_ID.pattern)]
    text: _text(300)
    type: QuestionType
    section: _text(100) | None = None
    help: _text(300) | None = None
    required: bool = False
    alert: bool = Field(False, description="Respostas desta pergunta aparecem como alerta.")
    options: list[Option] | None = None
    alert_options: list[Option] | None = Field(
        None, description="Escolhas que disparam o alerta (padrão: qualquer uma)."
    )

    @model_validator(mode="after")
    def _coherent(self):
        anamnese.check_question(self.model_dump())
        return self


def _checked(questions: list[Question]) -> list[Question]:
    anamnese.check_questions([q.model_dump() for q in questions])
    return questions


Questions = Annotated[list[Question], Field(max_length=anamnese.MAX_QUESTIONS)]


class TemplateCreate(BaseModel):
    name: _text(120)
    description: _text(500) | None = None
    questions: Questions = Field(default_factory=list, description="Perguntas do rascunho 1.")

    @model_validator(mode="after")
    def _unique_ids(self):
        _checked(self.questions)
        return self


class TemplateUpdate(BaseModel):
    name: _text(120) | None = None
    description: _text(500) | None = None
    active: bool | None = None


class DraftUpdate(BaseModel):
    questions: Questions

    @model_validator(mode="after")
    def _unique_ids(self):
        _checked(self.questions)
        return self


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    status: VersionStatus
    created_at: datetime
    published_at: datetime | None


class VersionOut(VersionSummary):
    template_id: uuid.UUID
    questions: list[dict[str, Any]]
    created_by: uuid.UUID | None
    published_by: uuid.UUID | None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    active: bool
    created_at: datetime
    published: VersionSummary | None = None
    draft: VersionSummary | None = None


class TemplateDetail(TemplateOut):
    versions: list[VersionSummary]


class ResponseCreate(BaseModel):
    template_id: uuid.UUID
    version_id: uuid.UUID = Field(
        description="Versão publicada que foi exibida; se o modelo mudou no meio, dá 409."
    )
    answers: dict[str, Any] = Field(description="{id da pergunta: resposta}.")


class AlertOut(BaseModel):
    question_id: str
    text: str
    answer: Any


class ResponseSummary(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    version_id: uuid.UUID
    version_number: int
    current: bool = Field(description="É a resposta mais recente deste modelo.")
    alerts: list[AlertOut]
    filled_by: uuid.UUID | None
    created_at: datetime


class ResponseDetail(ResponseSummary):
    questions: list[dict[str, Any]]
    answers: dict[str, Any]


class PatientAlert(AlertOut):
    template_id: uuid.UUID
    template_name: str
    response_id: uuid.UUID
    answered_at: datetime
