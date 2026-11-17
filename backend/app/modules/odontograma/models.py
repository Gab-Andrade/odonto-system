"""Odontograma 2D: legenda por clínica e histórico de marcações por paciente.

- `tooth_statuses`: a legenda da clínica (cárie, restauração, ausente...), com cor, tipo
  (patologia, planejado, realizado) e escopo (dente inteiro ou por face). Criada com uma
  legenda padrão na primeira vez que a clínica usa o odontograma; editável por admin e
  gestor. Tipo e escopo de um item não mudam depois de usado (gatilho na migração 0011).
- `odontogram_events`: append-only. Cada evento marca ou remove um item da legenda num
  dente (numeração FDI, 11–48 e 51–85) e, se o escopo for por face, numa face
  (M, D, O, V, L; O vale também como incisal e L como palatina). O odontograma em qualquer
  data é reconstruído aplicando os eventos até ela (`regras.rebuild`).

Gatilhos da migração 0011: o escopo do item tem de bater com a face informada, e só se
marca item ativo da legenda.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin


class StatusKind(StrEnum):
    PATOLOGIA = "patologia"
    PLANEJADO = "planejado"
    REALIZADO = "realizado"


class StatusScope(StrEnum):
    DENTE = "dente"
    FACE = "face"


class Display3D(StrEnum):
    COLORIR = "colorir"  # pinta a face ou o dente com a cor do item
    OCULTAR = "ocultar"  # esconde o dente no modelo 3D (ex.: ausente)


class EventAction(StrEnum):
    MARCAR = "marcar"
    REMOVER = "remover"


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(
        e,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class ToothStatus(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "tooth_statuses"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_tooth_statuses_id_clinic"),
        UniqueConstraint("clinic_id", "code", name="uq_tooth_statuses_clinic_code"),
    )

    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(7))  # #RRGGBB
    kind: Mapped[StatusKind] = mapped_column(_enum(StatusKind))
    scope: Mapped[StatusScope] = mapped_column(_enum(StatusScope))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    display_3d: Mapped[Display3D] = mapped_column(
        _enum(Display3D), default=Display3D.COLORIR, server_default="colorir"
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class OdontogramEvent(UUIDPkMixin, TenantMixin, Base):
    __tablename__ = "odontogram_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_odontogram_events_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["status_id", "clinic_id"],
            ["tooth_statuses.id", "tooth_statuses.clinic_id"],
            name="fk_odontogram_events_status_same_clinic",
            ondelete="RESTRICT",
        ),
        # Atendimento (opcional) do mesmo paciente.
        ForeignKeyConstraint(
            ["encounter_id", "patient_id", "clinic_id"],
            ["encounters.id", "encounters.patient_id", "encounters.clinic_id"],
            name="fk_odontogram_events_encounter_same_patient",
            ondelete="RESTRICT",
        ),
        Index("ix_odontogram_events_patient", "patient_id", "created_at"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    tooth: Mapped[int] = mapped_column(SmallInteger)
    face: Mapped[str | None] = mapped_column(String(1))
    status_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[EventAction] = mapped_column(_enum(EventAction))
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # clock_timestamp() (ver migração 0011): ordena os eventos de verdade.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class Dentition(StrEnum):
    PERMANENTE = "permanente"
    DECIDUA = "decidua"
    MISTA = "mista"


class ArchConfig(UUIDPkMixin, TenantMixin, Base):
    """Composição da arcada do paciente (append-only; a mais recente é a vigente).

    Ver `arcada.py`. Sem registro, a arcada é sugerida pela idade (não gravada).
    """

    __tablename__ = "dental_arch_configs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_dental_arch_configs_patient_same_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_dental_arch_configs_patient", "patient_id", "created_at"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column()
    dentition: Mapped[Dentition] = mapped_column(_enum(Dentition))
    teeth: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    notes: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # clock_timestamp(), como em odontogram_events: a ordem define a vigente.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
