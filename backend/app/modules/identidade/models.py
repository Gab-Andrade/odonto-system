"""Clínicas, usuários e vínculos usuário↔clínica.

Clínicas, usuários e vínculos são globais (sem RLS): o login precisa lê-los antes de
saber a clínica. O isolamento deles é feito na camada de serviço. As solicitações de
mudança de administrador pertencem à clínica (RLS).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPkMixin
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
    # Senha aleatória (cadastro/redefinição): só serve para definir a própria senha.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    # Tokens emitidos antes da última troca de senha deixam de valer.
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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


class MembershipInvite(UUIDPkMixin, TimestampMixin, Base):
    """Vínculo de um e-mail que já tem cadastro, à espera do código de uso único.

    Global (sem RLS), como os vínculos: o aceite acontece antes de haver clínica na sessão.
    Toda consulta filtra `clinic_id` ou `user_id` na camada de serviço. Ao aceitar, vira um
    `ClinicMembership` e o convite é apagado.
    """

    __tablename__ = "membership_invites"
    __table_args__ = (UniqueConstraint("user_id", "clinic_id", name="uq_invite_user_clinic"),)

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
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class AdminChangeAction(StrEnum):
    REBAIXAR = "rebaixar"
    DESATIVAR = "desativar"


class AdminChangeStatus(StrEnum):
    PENDENTE = "pendente"
    APROVADA = "aprovada"
    RECUSADA = "recusada"
    CANCELADA = "cancelada"
    EXPIRADA = "expirada"


def _str_enum(enum: type[StrEnum]) -> Enum:
    return Enum(
        enum,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        create_constraint=False,  # o CHECK é criado na migração
    )


class AdminChangeRequest(UUIDPkMixin, TenantMixin, TimestampMixin, Base):
    """Pedido para rebaixar ou desativar outro administrador (tabela da clínica, com RLS).

    Só vale depois que o próprio administrador alvo aceita. No máximo um
    pendente por alvo (índice único parcial na migração 0026).
    """

    __tablename__ = "admin_change_requests"
    __table_args__ = (
        Index(
            "uq_admin_change_requests_pending_target",
            "clinic_id",
            "target_user_id",
            unique=True,
            postgresql_where=text("status = 'pendente'"),
        ),
    )

    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[AdminChangeAction] = mapped_column(_str_enum(AdminChangeAction))
    new_role: Mapped[Role | None] = mapped_column(_str_enum(Role))
    reason: Mapped[str | None] = mapped_column(String(300))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[AdminChangeStatus] = mapped_column(
        _str_enum(AdminChangeStatus),
        default=AdminChangeStatus.PENDENTE,
        server_default=AdminChangeStatus.PENDENTE.value,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
