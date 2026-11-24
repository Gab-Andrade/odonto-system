import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.core.security import burn_password_check, hash_password, verify_password
from app.modules.identidade.models import Clinic, ClinicMembership, User


class InvalidCredentials(Exception):
    pass


class ClinicSelectionRequired(Exception):
    def __init__(self, clinics: list[Clinic]):
        super().__init__("usuário vinculado a mais de uma clínica")
        self.clinics = clinics


@dataclass(frozen=True)
class AuthResult:
    user: User
    clinic: Clinic
    role: Role


def normalize_email(email: str) -> str:
    return email.strip().lower()


class PasswordChangeRequired(Exception):
    """Senha aleatória (cadastro/redefinição): é preciso definir a própria antes de entrar."""


def verify_credentials(session: Session, email: str, password: str, *, lock: bool = False) -> User:
    """Usuário ativo com e-mail e senha corretos, ou InvalidCredentials (sem dizer o quê).

    Com `lock`, a linha só é travada **depois** de a senha conferir (quem não sabe a senha
    não segura a trava durante o hash) e é reconferida: se a senha mudou no meio, falha.
    """
    stmt = select(User).where(User.email == normalize_email(email))
    user = session.scalar(stmt)
    if user is None:
        burn_password_check(password)
        raise InvalidCredentials
    if not verify_password(password, user.password_hash) or not user.active:
        raise InvalidCredentials
    if lock:
        checked_hash = user.password_hash
        user = session.scalar(stmt.with_for_update().execution_options(populate_existing=True))
        if user is None or user.password_hash != checked_hash or not user.active:
            raise InvalidCredentials
    return user


def authenticate(
    session: Session, email: str, password: str, clinic_id: uuid.UUID | None
) -> AuthResult:
    user = verify_credentials(session, email, password)
    if user.must_change_password:
        raise PasswordChangeRequired

    rows = session.execute(
        select(ClinicMembership, Clinic)
        .join(Clinic, Clinic.id == ClinicMembership.clinic_id)
        .where(ClinicMembership.user_id == user.id, ClinicMembership.active, Clinic.active)
        .order_by(Clinic.name)
    ).all()

    if clinic_id is not None:
        rows = [r for r in rows if r.Clinic.id == clinic_id]
    if not rows:
        raise InvalidCredentials
    if len(rows) > 1:
        raise ClinicSelectionRequired([r.Clinic for r in rows])

    membership, clinic = rows[0]
    return AuthResult(user=user, clinic=clinic, role=membership.role)


def active_role(session: Session, user_id: uuid.UUID, clinic_id: uuid.UUID) -> Role | None:
    """Papel atual do usuário na clínica, ou None se o acesso foi revogado.

    Consultado a cada request: desativar usuário, vínculo ou clínica corta o acesso
    na hora, sem esperar o token expirar.
    """
    return session.scalar(
        select(ClinicMembership.role)
        .join(User, User.id == ClinicMembership.user_id)
        .join(Clinic, Clinic.id == ClinicMembership.clinic_id)
        .where(
            ClinicMembership.user_id == user_id,
            ClinicMembership.clinic_id == clinic_id,
            ClinicMembership.active,
            User.active,
            Clinic.active,
        )
    )


def active_memberships(session: Session, user_id: uuid.UUID) -> list[tuple[uuid.UUID, Role]]:
    """(clínica, papel) dos vínculos ativos do usuário em clínicas ativas."""
    rows = session.execute(
        select(ClinicMembership.clinic_id, ClinicMembership.role)
        .join(Clinic, Clinic.id == ClinicMembership.clinic_id)
        .where(ClinicMembership.user_id == user_id, ClinicMembership.active, Clinic.active)
    ).all()
    return [(c, r) for c, r in rows]


def session_role(
    session: Session, user_id: uuid.UUID, clinic_id: uuid.UUID, issued_at: datetime
) -> Role | None:
    """Papel para um token emitido em `issued_at`, ou None se ele não vale mais.

    Além de `active_role`: o token perde a validade quando a senha é trocada ou redefinida
    depois dele, e quem está com senha aleatória não usa o sistema até defini-la.
    """
    row = session.execute(
        select(ClinicMembership.role, User.must_change_password, User.password_changed_at)
        .join(User, User.id == ClinicMembership.user_id)
        .join(Clinic, Clinic.id == ClinicMembership.clinic_id)
        .where(
            ClinicMembership.user_id == user_id,
            ClinicMembership.clinic_id == clinic_id,
            ClinicMembership.active,
            User.active,
            Clinic.active,
        )
    ).first()
    if row is None or row.must_change_password:
        return None
    # `issued_at` vem em milissegundos (claim `iat_ms`); compara na mesma precisão.
    changed = row.password_changed_at
    if changed is not None and issued_at < changed.replace(
        microsecond=changed.microsecond // 1000 * 1000
    ):
        return None
    return row.role


def create_clinic_with_admin(
    session: Session,
    *,
    clinic_name: str,
    clinic_slug: str,
    admin_email: str,
    admin_name: str,
    admin_password: str,
) -> tuple[Clinic, User]:
    clinic = Clinic(name=clinic_name, slug=clinic_slug)
    email = normalize_email(admin_email)
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, full_name=admin_name, password_hash=hash_password(admin_password))
        session.add(user)
    session.add(clinic)
    session.flush()
    session.add(ClinicMembership(user_id=user.id, clinic_id=clinic.id, role=Role.ADMIN))
    session.flush()
    return clinic, user


def team(session: Session, clinic_id: uuid.UUID) -> list[tuple[User, Role]]:
    """Membros ativos da clínica (tabelas globais: o filtro por clínica é explícito)."""
    rows = session.execute(
        select(User, ClinicMembership.role)
        .join(ClinicMembership, ClinicMembership.user_id == User.id)
        .where(ClinicMembership.clinic_id == clinic_id, ClinicMembership.active, User.active)
        .order_by(User.full_name)
    ).all()
    return [(u, r) for u, r in rows]
