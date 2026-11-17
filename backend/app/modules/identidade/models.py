"""Clínicas, usuários e vínculos usuário↔clínica.

Estas tabelas são globais (sem RLS): o login precisa lê-las antes de saber a clínica.
O isolamento delas é feito na camada de serviço.
"""

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TimestampMixin, UUIDPkMixin
from app.core.roles import Role


class Clinic(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class User(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)  # sempre minúsculo
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    cro: Mapped[str | None] = mapped_column(String(30))  # registro no CRO, para dentistas
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    memberships: Mapped[list["ClinicMembership"]] = relationship(back_populates="user")


class ClinicMembership(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "clinic_memberships"
    __table_args__ = (UniqueConstraint("user_id", "clinic_id", name="uq_membership_user_clinic"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
            validate_strings=True,
            create_constraint=False,  # o CHECK é criado na migração
        )
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    user: Mapped[User] = relationship(back_populates="memberships")
    clinic: Mapped[Clinic] = relationship()
