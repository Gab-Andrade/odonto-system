"""Pacientes: cadastro e consentimentos (LGPD).

O cadastro é dado pessoal e a ficha abre o prontuário, então a leitura também é auditada
(ver router). Paciente não é excluído, só desativado: o prontuário tem guarda mínima de
20 anos (Lei 13.787/2018).

`search_name` é o nome (e o nome social) em minúsculas e sem acento, gerado pelo service,
com índice trigrama para a busca por trecho do nome.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class Sex(StrEnum):
    FEMININO = "feminino"
    MASCULINO = "masculino"
    INTERSEXO = "intersexo"


class ConsentPurpose(StrEnum):
    TRATAMENTO_DADOS = "tratamento_dados"  # dados pessoais e de saúde para o atendimento
    COMUNICACAO = "comunicacao"  # lembretes e contato por WhatsApp/e-mail
    USO_IMAGEM = "uso_imagem"  # fotos para divulgação


class ConsentGivenBy(StrEnum):
    PACIENTE = "paciente"
    RESPONSAVEL = "responsavel"


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(
        e,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class Patient(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_patients_id_clinic"),
        # CPF é opcional, mas único na clínica quando informado.
        Index(
            "uq_patients_clinic_cpf",
            "clinic_id",
            "cpf",
            unique=True,
            postgresql_where=text("cpf IS NOT NULL"),
        ),
        Index(
            "ix_patients_search_name_trgm",
            "search_name",
            postgresql_using="gin",
            postgresql_ops={"search_name": "gin_trgm_ops"},
        ),
    )

    full_name: Mapped[str] = mapped_column(String(200))
    social_name: Mapped[str | None] = mapped_column(String(200))
    search_name: Mapped[str] = mapped_column(String(401))
    birth_date: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[Sex | None] = mapped_column(_enum(Sex))
    cpf: Mapped[str | None] = mapped_column(String(11))  # só dígitos
    phone: Mapped[str] = mapped_column(String(15))  # só dígitos
    phone_alt: Mapped[str | None] = mapped_column(String(15))
    email: Mapped[str | None] = mapped_column(String(254))

    zip_code: Mapped[str | None] = mapped_column(String(8))
    street: Mapped[str | None] = mapped_column(String(200))
    number: Mapped[str | None] = mapped_column(String(20))
    complement: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))

    # Responsável legal (obrigatório para menores de 18 anos).
    guardian_name: Mapped[str | None] = mapped_column(String(200))
    guardian_cpf: Mapped[str | None] = mapped_column(String(11))
    guardian_phone: Mapped[str | None] = mapped_column(String(15))
    guardian_relationship: Mapped[str | None] = mapped_column(String(50))

    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class PatientConsent(UUIDPkMixin, TenantMixin, Base):
    """Evento de consentimento (aceite ou revogação). Append-only: o estado atual de cada
    finalidade é o evento mais recente."""

    __tablename__ = "patient_consents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_patient_consents_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_patient_consents_patient", "patient_id", "purpose", "created_at"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    purpose: Mapped[ConsentPurpose] = mapped_column(_enum(ConsentPurpose))
    granted: Mapped[bool] = mapped_column(Boolean)  # False = revogação
    given_by: Mapped[ConsentGivenBy] = mapped_column(_enum(ConsentGivenBy))
    term_version: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
