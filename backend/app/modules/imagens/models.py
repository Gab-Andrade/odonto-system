"""Exames de imagem (raio-X) anexados ao prontuário do paciente.

Fase 5.3, versão simples: arquivo DICOM guardado no armazenamento local (`app.core.storage`),
com os metadados lidos pelo pydicom e a classificação clínica (tipo, dentes, data). Sem
Orthanc e sem visualizador por enquanto.

O arquivo e o que veio dele são imutáveis (gatilho no banco). Não se apaga exame (guarda
do prontuário): um envio errado é invalidado com motivo e some da listagem padrão.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class ImageKind(StrEnum):
    PERIAPICAL = "periapical"
    INTERPROXIMAL = "interproximal"
    PANORAMICA = "panoramica"
    TOMOGRAFIA = "tomografia"
    OUTRO = "outro"


class ImagingExam(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "imaging_exams"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_imaging_exams_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_imaging_exams_encounter_same_clinic",
            ondelete="RESTRICT",
        ),
        # O mesmo arquivo não é anexado duas vezes ao mesmo paciente.
        UniqueConstraint("clinic_id", "patient_id", "sha256", name="uq_imaging_exams_file"),
        Index("ix_imaging_exams_patient", "patient_id", "exam_date"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    kind: Mapped[ImageKind] = mapped_column(
        Enum(
            ImageKind,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
            validate_strings=True,
            create_constraint=False,
        )
    )
    teeth: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    exam_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(1000))

    # Arquivo (imutável).
    file_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(200))

    # Metadados DICOM (imutáveis).
    modality: Mapped[str | None] = mapped_column(String(16))
    study_uid: Mapped[str | None] = mapped_column(String(64))
    series_uid: Mapped[str | None] = mapped_column(String(64))
    sop_uid: Mapped[str | None] = mapped_column(String(64))
    study_date: Mapped[date | None] = mapped_column(Date)
    study_description: Mapped[str | None] = mapped_column(String(200))
    series_description: Mapped[str | None] = mapped_column(String(200))
    body_part: Mapped[str | None] = mapped_column(String(64))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    rows: Mapped[int | None] = mapped_column()
    columns: Mapped[int | None] = mapped_column()
    dicom_patient_name: Mapped[str | None] = mapped_column(String(200))
    dicom_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # RESTRICT (não SET NULL): o gatilho do banco não deixa esses campos mudarem.
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    invalidation_reason: Mapped[str | None] = mapped_column(String(300))
