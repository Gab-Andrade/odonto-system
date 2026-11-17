import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.precificacao.models import (
    ImportStatus,
    ScopeType,
    TableKind,
    TableStatus,
    VersionStatus,
)

# Limites alinhados às colunas Numeric(12,2) e Numeric(7,4).
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Percent = Annotated[
    Decimal, Field(ge=Decimal("-100"), le=Decimal("999.9999"), max_digits=7, decimal_places=4)
]
ProcedureCode = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]


# ---------- Tabelas ----------


class TableCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: str | None = Field(default=None, max_length=500)
    parent_table_id: uuid.UUID | None = None
    adjustment_pct: Percent | None = Field(
        default=None, description="Ajuste sobre a tabela-pai, em %. Ex.: 15 = +15%."
    )
    kind: TableKind = Field(
        default=TableKind.FIXA,
        description="'fixa': preços digitados/importados. 'calculada': gerados por fórmula.",
    )
    calc_dentist_id: uuid.UUID | None = Field(
        default=None,
        description="Tabela calculada: usa as variáveis deste dentista (senão, as da clínica).",
    )


class TableUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    description: str | None = Field(default=None, max_length=500)
    status: TableStatus | None = None


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    parent_table_id: uuid.UUID | None
    status: TableStatus
    kind: TableKind
    calc_dentist_id: uuid.UUID | None
    created_at: datetime


# ---------- Versões e itens ----------


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    version: int
    status: VersionStatus
    adjustment_pct: Decimal | None
    valid_from: date | None
    published_at: datetime | None
    published_by: uuid.UUID | None
    calculated_at: datetime | None


class FormulaStep(BaseModel):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    expressao: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class VersionUpdate(BaseModel):
    adjustment_pct: Percent | None = None
    formula: list[FormulaStep] | None = Field(
        default=None, max_length=30, description="Só para tabelas calculadas."
    )


class ItemIn(BaseModel):
    procedure_code: ProcedureCode
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    category: str | None = Field(default=None, max_length=100)
    price: Money
    custom_fields: dict[str, Annotated[str, StringConstraints(max_length=500)]] | None = None


class ItemsReplace(BaseModel):
    items: list[ItemIn] = Field(max_length=5000)

    @field_validator("items")
    @classmethod
    def _no_duplicate_codes(cls, items: list[ItemIn]) -> list[ItemIn]:
        counts = Counter(i.procedure_code for i in items)
        dup = sorted(code for code, n in counts.items() if n > 1)
        if dup:
            raise ValueError(f"Códigos de procedimento repetidos: {', '.join(dup)}")
        return items


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    procedure_code: str
    description: str
    category: str | None
    price: Decimal
    custom_fields: dict[str, str] | None


class PublishIn(BaseModel):
    valid_from: date | None = Field(default=None, description="Padrão: hoje.")


# ---------- Atribuições ----------


class AssignmentCreate(BaseModel):
    table_id: uuid.UUID
    scope_type: ScopeType
    scope_id: uuid.UUID | None = Field(
        default=None, description="Dentista (id do usuário) ou convênio. Vazio para 'clinica'."
    )
    priority: int | None = Field(
        default=None, ge=0, le=1000, description="Menor vence. Padrão por tipo de escopo."
    )


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    scope_type: ScopeType
    scope_id: uuid.UUID | None
    priority: int
    created_at: datetime


# ---------- Resolução ----------


class ResolveIn(BaseModel):
    procedure_code: ProcedureCode
    dentist_id: uuid.UUID | None = None
    insurer_id: uuid.UUID | None = None
    effective_on: date | None = Field(default=None, description="Padrão: hoje.")


class ResolutionOut(BaseModel):
    procedure_code: str
    description: str
    category: str | None
    price: Decimal
    table_id: uuid.UUID
    version_id: uuid.UUID
    effective_on: date
    trace: list[dict[str, Any]]


class SnapshotOut(ResolutionOut):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dentist_id: uuid.UUID | None
    insurer_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime


# ---------- Importação ----------

ColumnMap = dict[str, str | None]


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    status: ImportStatus
    filename: str
    file_size: int
    detected: dict[str, Any]
    headers: list[str]
    column_map: ColumnMap | None
    extra_columns: list[str] | None
    report: dict[str, Any] | None
    applied_version_id: uuid.UUID | None
    created_at: datetime
    amostra: list[dict[str, Any]] = Field(
        default_factory=list, description="Primeiras linhas lidas, para conferir o mapeamento."
    )


class ImportJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    status: ImportStatus
    filename: str
    created_at: datetime


class ImportValidateIn(BaseModel):
    column_map: ColumnMap | None = Field(
        default=None,
        description="Campo → nome da coluna. Vazio: usa o perfil ou a sugestão automática.",
        examples=[{"procedure_code": "Código", "description": "Procedimento", "price": "Valor"}],
    )
    extra_columns: list[Annotated[str, StringConstraints(max_length=255)]] | None = Field(
        default=None, max_length=50, description="Colunas a guardar como campos extras do item."
    )
    profile_id: uuid.UUID | None = None


class ImportApplyIn(BaseModel):
    ignorar_erros: bool = Field(
        default=False, description="Aplica só as linhas válidas, descartando as com erro."
    )


class ImportApplyOut(BaseModel):
    importacao: ImportJobSummary
    versao: VersionOut


class ProfileCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    column_map: ColumnMap
    extra_columns: list[Annotated[str, StringConstraints(max_length=255)]] = Field(
        default_factory=list, max_length=50
    )


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    column_map: ColumnMap
    extra_columns: list[str]
    created_at: datetime


# ---------- Fórmulas, fichas técnicas e variáveis ----------


class FormulaOut(BaseModel):
    formula: list[FormulaStep]
    entradas_do_sistema: dict[str, str]
    funcoes: dict[str, str]
    variaveis_sugeridas: dict[str, str]


class SheetItemIn(BaseModel):
    material_id: uuid.UUID
    quantity: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=4)]


class SheetIn(BaseModel):
    procedure_code: ProcedureCode
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    category: str | None = Field(default=None, max_length=100)
    duration_minutes: int = Field(gt=0, le=1440, description="Tempo do procedimento.")
    items: list[SheetItemIn] = Field(default_factory=list, max_length=100)


class SheetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    material_id: uuid.UUID
    quantity: Decimal


class SheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    procedure_code: str
    description: str
    category: str | None
    duration_minutes: int
    items: list[SheetItemOut] = Field(default_factory=list)
    updated_at: datetime


class VariableIn(BaseModel):
    key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    value: Annotated[Decimal, Field(max_digits=14, decimal_places=4)]
    label: str | None = Field(default=None, max_length=120)
    dentist_id: uuid.UUID | None = Field(
        default=None, description="Vazio: valor padrão da clínica. Preenchido: valor do dentista."
    )


class VariableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    label: str | None
    value: Decimal
    dentist_id: uuid.UUID | None
    updated_at: datetime


class FormulaTestIn(BaseModel):
    procedure_code: ProcedureCode
    formula: list[FormulaStep] | None = Field(
        default=None, max_length=30, description="Vazio: usa a fórmula padrão."
    )
    dentist_id: uuid.UUID | None = None


class CalculationOut(BaseModel):
    procedure_code: str
    description: str
    price: Decimal
    trace: dict[str, Any]


class RecalcOut(BaseModel):
    versao: VersionOut
    calculados: int
    erros: list[dict[str, str]]


class ItemCalcOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    procedure_code: str
    price: Decimal
    calc_trace: dict[str, Any] | None
