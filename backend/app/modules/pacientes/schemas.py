import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.modules.pacientes import dados
from app.modules.pacientes.models import ConsentGivenBy, ConsentPurpose, Sex


def _text(max_length: int, min_length: int = 1):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
    ]


Name = _text(200)
Cpf = Annotated[str, AfterValidator(dados.normalize_cpf)]
Phone = Annotated[str, AfterValidator(dados.normalize_phone)]
ZipCode = Annotated[str, Field(pattern=r"^\d{5}-?\d{3}$"), AfterValidator(dados.only_digits)]
State = Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{2}$")]


class PatientFields(BaseModel):
    """Campos editáveis do cadastro (comuns a criação e alteração)."""

    social_name: Name | None = None
    birth_date: date | None = None
    sex: Sex | None = None
    cpf: Cpf | None = None
    phone_alt: Phone | None = None
    email: EmailStr | None = None
    zip_code: ZipCode | None = None
    street: _text(200) | None = None
    number: _text(20) | None = None
    complement: _text(100) | None = None
    district: _text(100) | None = None
    city: _text(100) | None = None
    state: State | None = None
    guardian_name: Name | None = None
    guardian_cpf: Cpf | None = None
    guardian_phone: Phone | None = None
    guardian_relationship: _text(50) | None = None
    notes: _text(2000) | None = None

    @field_validator("birth_date")
    @classmethod
    def _birth_not_future(cls, value: date | None) -> date | None:
        if value is not None and (value > date.today() or value.year < 1900):
            raise ValueError("Data de nascimento inválida.")
        return value


class PatientCreate(PatientFields):
    full_name: Name
    phone: Phone


class PatientUpdate(PatientFields):
    """Só os campos enviados são alterados; `null` limpa um campo opcional."""

    full_name: Name | None = None
    phone: Phone | None = None
    active: bool | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    social_name: str | None
    birth_date: date | None
    sex: Sex | None
    cpf: str | None
    phone: str
    phone_alt: str | None
    email: str | None
    zip_code: str | None
    street: str | None
    number: str | None
    complement: str | None
    district: str | None
    city: str | None
    state: str | None
    guardian_name: str | None
    guardian_cpf: str | None
    guardian_phone: str | None
    guardian_relationship: str | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class PatientSummary(BaseModel):
    """Linha da busca: dados mínimos para reconhecer o paciente, com CPF mascarado."""

    id: uuid.UUID
    full_name: str
    social_name: str | None
    birth_date: date | None
    cpf_mascarado: str | None
    phone: str
    active: bool


class ConsentIn(BaseModel):
    purpose: ConsentPurpose
    granted: bool = Field(description="false registra a revogação.")
    given_by: ConsentGivenBy = ConsentGivenBy.PACIENTE
    term_version: _text(40) | None = None
    notes: _text(500) | None = None


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purpose: ConsentPurpose
    granted: bool
    given_by: ConsentGivenBy
    term_version: str | None
    notes: str | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class ConsentsOut(BaseModel):
    atuais: dict[ConsentPurpose, ConsentOut | None]
    historico: list[ConsentOut]
