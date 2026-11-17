"""Prontuário — anamnese configurável.

- `anamnesis_templates`: modelos de formulário da clínica (nome único por clínica).
- `anamnesis_template_versions`: versões de cada modelo. Fluxo rascunho → publicada →
  substituída (quando outra é publicada). No máximo um rascunho e uma publicada por modelo
  (índices únicos parciais). As perguntas (JSONB) de uma versão que saiu de rascunho não
  mudam mais: um gatilho na migração 0009 recusa a alteração.
- `anamnesis_responses`: respostas de um paciente a uma versão publicada. Imutáveis
  (append-only): responder de novo cria outra resposta, e a mais recente de cada modelo é a
  atual. `alerts` guarda, no momento do preenchimento, as respostas marcadas como alerta
  (ex.: alergia), com o texto da pergunta, para o cabeçalho do paciente.

A FK composta (version_id, template_id, clinic_id) garante que a versão pertence ao modelo
informado e à mesma clínica.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class VersionStatus(StrEnum):
    RASCUNHO = "rascunho"
    PUBLICADA = "publicada"
    SUBSTITUIDA = "substituida"


class AnamnesisTemplate(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "anamnesis_templates"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_anamnesis_templates_id_clinic"),
        UniqueConstraint("clinic_id", "name", name="uq_anamnesis_templates_clinic_name"),
    )

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class AnamnesisTemplateVersion(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "anamnesis_template_versions"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_anamnesis_template_versions_id_clinic"),
        UniqueConstraint(
            "id", "template_id", "clinic_id", name="uq_anamnesis_template_versions_id_template"
        ),
        UniqueConstraint(
            "template_id", "number", name="uq_anamnesis_template_versions_template_number"
        ),
        ForeignKeyConstraint(
            ["template_id", "clinic_id"],
            ["anamnesis_templates.id", "anamnesis_templates.clinic_id"],
            name="fk_anamnesis_template_versions_template_same_clinic",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_anamnesis_template_versions_one_draft",
            "template_id",
            unique=True,
            postgresql_where=text("status = 'rascunho'"),
        ),
        Index(
            "uq_anamnesis_template_versions_one_published",
            "template_id",
            unique=True,
            postgresql_where=text("status = 'publicada'"),
        ),
    )

    template_id: Mapped[uuid.UUID] = mapped_column()
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(
            VersionStatus,
            native_enum=False,
            length=20,
            values_callable=lambda x: [m.value for m in x],
            validate_strings=True,
            create_constraint=False,  # o CHECK é criado na migração
        ),
        default=VersionStatus.RASCUNHO,
        server_default=VersionStatus.RASCUNHO.value,
    )
    # Lista de perguntas (formato em schemas.Question).
    questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class AnamnesisResponse(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "anamnesis_responses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_anamnesis_responses_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["version_id", "template_id", "clinic_id"],
            [
                "anamnesis_template_versions.id",
                "anamnesis_template_versions.template_id",
                "anamnesis_template_versions.clinic_id",
            ],
            name="fk_anamnesis_responses_version_same_template",
            ondelete="RESTRICT",
        ),
        Index("ix_anamnesis_responses_patient", "patient_id", "template_id", "created_at"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    template_id: Mapped[uuid.UUID] = mapped_column()
    version_id: Mapped[uuid.UUID] = mapped_column()
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB)
    alerts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    filled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
