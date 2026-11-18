import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints


class ParamOut(BaseModel):
    name: str
    label: str
    type: Literal["inteiro", "termos"]
    default: Any
    minimum: int | None = None
    maximum: int | None = None


class RuleOut(BaseModel):
    code: str
    title: str
    description: str
    category: str = Field(description="clinico, orcamento, agenda ou financeiro.")
    severity: str = Field(description="alta, media ou baixa.")
    roles: list[str] = Field(description="Papéis que veem os alertas desta regra.")
    enabled: bool
    params: dict[str, Any] = Field(description="Parâmetros em vigor (padrões + os da clínica).")
    param_spec: list[ParamOut]
    customized: bool = Field(description="A clínica já salvou uma configuração própria.")
    updated_at: datetime | None
    updated_by: uuid.UUID | None


class RuleIn(BaseModel):
    enabled: bool = True
    params: dict[str, Any] = Field(
        default_factory=dict, description="Só os que mudam; os omitidos voltam ao padrão."
    )


class AlertOut(BaseModel):
    code: str = Field(description="Regra que gerou o alerta.")
    title: str
    severity: str
    category: str
    key: str = Field(description="Identifica o alerta na regra (para dispensar).")
    patient_id: uuid.UUID | None
    patient_name: str | None
    patient_phone: str | None
    dentist_id: uuid.UUID | None = Field(description="Dentista responsável, quando houver.")
    since: date | None = Field(description="Data do fato que originou o alerta.")
    detail: str
    ref_type: str = Field(description="paciente, plano, item_plano ou atendimento.")
    ref_id: uuid.UUID
    dismissed_until: date | None = Field(
        None, description="Preenchido só com incluir_dispensados: escondido até esta data."
    )


class SummaryOut(BaseModel):
    total: int
    by_rule: dict[str, int] = Field(description="Alertas ativos por regra visível e ligada.")


class DismissIn(BaseModel):
    code: str
    key: str
    until: date | None = Field(None, description="Padrão: daqui a 30 dias (máximo 365).")
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class RestoreIn(BaseModel):
    code: str
    key: str


class DismissalOut(BaseModel):
    code: str
    key: str
    until: date
    created_at: datetime
