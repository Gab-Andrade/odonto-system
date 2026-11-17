"""Agenda: cadeiras, agendamentos de consulta e bloqueios de horário.

Consultas e bloqueios ficam na mesma tabela (`appointments.kind`) para que as mesmas
constraints de exclusão impeçam conflito entre eles. As constraints são criadas na
migração 0008 (não aparecem aqui):

- `excl_appointments_dentist_overlap`: mesmo dentista, horários sobrepostos;
- `excl_appointments_chair_overlap`: mesma cadeira, horários sobrepostos.

Ambas usam `tstzrange(starts_at, ends_at, '[)')` (um termina às 10h e outro começa às 10h
não conflitam) e só valem para status que ocupam o horário (agendado, confirmado,
atendido). Falta e cancelamento liberam o horário.

`appointment_events` é o histórico (criação, reagendamento, mudança de status), append-only.
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
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class EntryKind(StrEnum):
    CONSULTA = "consulta"
    BLOQUEIO = "bloqueio"


class AppointmentStatus(StrEnum):
    AGENDADO = "agendado"
    CONFIRMADO = "confirmado"
    ATENDIDO = "atendido"
    FALTA = "falta"
    CANCELADO = "cancelado"


# Status que ocupam o horário (os mesmos do WHERE das constraints de exclusão).
OCCUPYING = (AppointmentStatus.AGENDADO, AppointmentStatus.CONFIRMADO, AppointmentStatus.ATENDIDO)


class EventAction(StrEnum):
    CRIADO = "criado"
    REAGENDADO = "reagendado"
    ALTERADO = "alterado"
    STATUS = "status"


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(
        e,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class Chair(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "chairs"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_chairs_id_clinic"),
        UniqueConstraint("clinic_id", "name", name="uq_chairs_clinic_name"),
    )

    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class Appointment(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_appointments_id_clinic"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_appointments_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["chair_id", "clinic_id"],
            ["chairs.id", "chairs.clinic_id"],
            name="fk_appointments_chair_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_appointments_starts_at", "clinic_id", "starts_at"),
        Index("ix_appointments_patient", "patient_id", "starts_at"),
    )

    kind: Mapped[EntryKind] = mapped_column(_enum(EntryKind))
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum(AppointmentStatus),
        default=AppointmentStatus.AGENDADO,
        server_default=AppointmentStatus.AGENDADO.value,
    )
    # Consulta: paciente e dentista obrigatórios. Bloqueio: sem paciente, com dentista
    # e/ou cadeira (CHECKs na migração).
    patient_id: Mapped[uuid.UUID | None] = mapped_column()
    # Usuário com vínculo ativo de dentista ou admin (validado no service; `users` é global).
    dentist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    chair_id: Mapped[uuid.UUID | None] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    procedure: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(1000))
    status_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class AppointmentEvent(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "appointment_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_appointment_events_appointment_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_appointment_events_appointment", "appointment_id", "created_at"),
    )

    appointment_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[EventAction] = mapped_column(_enum(EventAction))
    status: Mapped[AppointmentStatus] = mapped_column(_enum(AppointmentStatus))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
