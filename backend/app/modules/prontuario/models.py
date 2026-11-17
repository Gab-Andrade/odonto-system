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

Atendimento e evolução clínica:

- `encounters`: o atendimento (entidade própria; o agendamento é opcional, cobrindo encaixe
  e urgência). Aberto pelo dentista que atende; depois de fechado não muda mais.
- `clinical_notes`: evoluções e adendos, append-only. Correção é sempre um adendo sobre a
  evolução (`amends_id`), feito pelo mesmo autor. `performed_at` é a data do ato clínico
  (até 7 dias para trás); `created_at` é a data real do registro. `content_hash` (SHA-256)
  fixa o conteúdo e é o que uma assinatura assina.
- `encounter_transfers`: passagem de um atendimento aberto para outro dentista (pelo
  admin, ex.: o dentista saiu da clínica), append-only. O gatilho da migração 0012 só
  deixa `encounters.dentist_id` mudar com esse registro na mesma transação.
- `clinical_note_signatures`: assinaturas das evoluções, append-only. Hoje só a assinatura
  eletrônica simples (usuário autenticado); o campo `signature`/`certificate` fica pronto
  para ICP-Brasil.

Gatilhos da migração 0010 garantem no banco: evolução só no atendimento aberto e pelo
dentista dele; adendo só sobre evolução e pelo autor dela; atendimento fechado não muda.
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
    Text,
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


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(
        e,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class EncounterStatus(StrEnum):
    ABERTO = "aberto"
    FECHADO = "fechado"


class NoteKind(StrEnum):
    EVOLUCAO = "evolucao"
    ADENDO = "adendo"


class SignatureMethod(StrEnum):
    SIMPLES = "simples"  # usuário autenticado no sistema
    ICP_BRASIL = "icp_brasil"  # previsto: certificado digital


class Encounter(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_encounters_id_clinic"),
        UniqueConstraint("id", "patient_id", "clinic_id", name="uq_encounters_id_patient"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_encounters_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_encounters_appointment_same_clinic",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_encounters_appointment",
            "appointment_id",
            unique=True,
            postgresql_where=text("appointment_id IS NOT NULL"),
        ),
        Index("ix_encounters_patient", "patient_id", "started_at"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    # Quem atende: usuário com vínculo ativo de dentista ou admin (validado pelo papel).
    dentist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    appointment_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[EncounterStatus] = mapped_column(
        _enum(EncounterStatus),
        default=EncounterStatus.ABERTO,
        server_default=EncounterStatus.ABERTO.value,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ClinicalNote(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "clinical_notes"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_clinical_notes_id_clinic"),
        UniqueConstraint("id", "encounter_id", "clinic_id", name="uq_clinical_notes_id_encounter"),
        ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_clinical_notes_encounter_same_patient",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["amends_id", "encounter_id", "clinic_id"],
            ["clinical_notes.id", "clinical_notes.encounter_id", "clinical_notes.clinic_id"],
            name="fk_clinical_notes_amends_same_encounter",
            ondelete="RESTRICT",
        ),
        Index("ix_clinical_notes_patient", "patient_id", "performed_at"),
        Index("ix_clinical_notes_encounter", "encounter_id", "created_at"),
    )

    encounter_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[NoteKind] = mapped_column(_enum(NoteKind))
    amends_id: Mapped[uuid.UUID | None] = mapped_column()
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    content: Mapped[str] = mapped_column(Text)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicalNoteSignature(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "clinical_note_signatures"
    __table_args__ = (
        ForeignKeyConstraint(
            ["note_id", "clinic_id"],
            ["clinical_notes.id", "clinical_notes.clinic_id"],
            name="fk_clinical_note_signatures_note_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_clinical_note_signatures_note", "note_id"),
    )

    note_id: Mapped[uuid.UUID] = mapped_column()
    signer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    method: Mapped[SignatureMethod] = mapped_column(_enum(SignatureMethod))
    content_hash: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str | None] = mapped_column(Text)  # ICP-Brasil: assinatura (CMS/PAdES)
    certificate: Mapped[str | None] = mapped_column(Text)  # ICP-Brasil: certificado do signatário
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EncounterTransfer(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "encounter_transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "clinic_id"],
            ["encounters.id", "encounters.clinic_id"],
            name="fk_encounter_transfers_encounter_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_encounter_transfers_encounter", "encounter_id", "created_at"),
    )

    encounter_id: Mapped[uuid.UUID] = mapped_column()
    from_dentist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    to_dentist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(300))
    transferred_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
