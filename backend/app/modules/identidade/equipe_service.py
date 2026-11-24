"""Cadastro de equipe da clínica: membros, convites, senhas e pedidos de mudança de admin.

Usuários, vínculos e convites são tabelas **globais** (sem RLS): toda consulta a
`clinic_memberships` e `membership_invites` aqui filtra por `clinic_id` (ou pelo próprio
usuário) de forma explícita. Os dados da pessoa (`users`: nome, CRO, senha) podem ser
compartilhados com outras clínicas; por isso só são alterados por aqui quando a pessoa só
tem vínculo com esta clínica.

- E-mail novo: o usuário nasce com senha aleatória e `must_change_password`, que só
  serve para ele definir a própria senha.
- E-mail que já tem cadastro: vira **convite** com código de uso único, que a clínica
  entrega pessoalmente. O vínculo só existe depois que a pessoa entra com a senha dela
  e digita o código; quem só conhece a senha (por exemplo, quem a cadastrou em outra
  clínica) não ganha acesso.
- Administrador: a clínica nunca fica sem admin ativo. O próprio admin deixa de ser
  admin direto (se sobrar outro). Rebaixar ou desativar **outro** admin vira pedido, que
  só vale quando o próprio admin alvo aceita; expira em `REQUEST_TTL`.
- Senha de outro admin não é redefinida aqui (seria um atalho para tomar a conta dele).

As funções da clínica recebem a sessão de tenant do endpoint (o RLS cobre os pedidos) e
não fazem commit.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.roles import Role
from app.core.security import hash_password, verify_password
from app.modules.identidade.models import (
    AdminChangeAction,
    AdminChangeRequest,
    AdminChangeStatus,
    Clinic,
    ClinicMembership,
    MembershipInvite,
    User,
)
from app.modules.identidade.service import (
    InvalidCredentials,
    PasswordChangeRequired,
    normalize_email,
    verify_credentials,
)

REQUEST_TTL = timedelta(days=7)
INVITE_TTL = timedelta(days=7)
# Sem caracteres que se confundem (0/o, 1/l/i), para ditar ou copiar à mão.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class TeamError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(TeamError):
    pass


class Forbidden(TeamError):
    pass


class RuleViolation(TeamError):
    pass


class InvalidCode(TeamError):
    pass


@dataclass(frozen=True)
class Member:
    user: User
    membership: ClinicMembership
    other_clinics: bool


@dataclass(frozen=True)
class Added:
    """Resultado de `add_member`: membro novo (com senha) ou convite (com código)."""

    member: Member | None = None
    password: str | None = None
    invite: MembershipInvite | None = None
    code: str | None = None


def _random(groups: int, size: int) -> str:
    chars = "".join(secrets.choice(_ALPHABET) for _ in range(groups * size))
    return "-".join(chars[i : i + size] for i in range(0, len(chars), size))


def generate_password() -> str:
    """12 caracteres aleatórios em 3 grupos (ex.: `k7mp-x2qa-9tbw`), ~59 bits."""
    return _random(3, 4)


def generate_code() -> str:
    """Código de convite: 10 caracteres em 2 grupos (ex.: `k7mpx-2qa9t`), ~49 bits."""
    return _random(2, 5)


def _normalize_code(code: str) -> str:
    return code.strip().lower().replace(" ", "")


def _now() -> datetime:
    return datetime.now(UTC)


def _set_password(user: User, password: str, *, temporary: bool) -> None:
    user.password_hash = hash_password(password)
    user.must_change_password = temporary
    user.password_changed_at = _now()  # derruba as sessões abertas


def _other_clinics_expr(clinic_id: uuid.UUID):
    """A pessoa tem vínculo, ou convite ainda válido, em outra clínica."""
    other = ClinicMembership.__table__.alias("other")
    invite = MembershipInvite.__table__.alias("other_invite")
    return or_(
        exists().where(other.c.user_id == User.id, other.c.clinic_id != clinic_id),
        exists().where(
            invite.c.user_id == User.id,
            invite.c.clinic_id != clinic_id,
            invite.c.expires_at > func.now(),
        ),
    )


def list_members(db: Session, clinic_id: uuid.UUID, *, include_inactive: bool) -> list[Member]:
    stmt = (
        select(User, ClinicMembership, _other_clinics_expr(clinic_id))
        .join(ClinicMembership, ClinicMembership.user_id == User.id)
        .where(ClinicMembership.clinic_id == clinic_id)
        .order_by(User.full_name)
    )
    if not include_inactive:
        stmt = stmt.where(ClinicMembership.active, User.active)
    return [Member(u, m, bool(o)) for u, m, o in db.execute(stmt).all()]


def get_member(
    db: Session, clinic_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> Member:
    stmt = (
        select(User, ClinicMembership)
        .join(ClinicMembership, ClinicMembership.user_id == User.id)
        .where(ClinicMembership.clinic_id == clinic_id, User.id == user_id)
    )
    if lock:
        # Trava o usuário também: "outra clínica" não pode mudar entre a checagem e a escrita
        # (vínculo e convite novos travam a linha do usuário).
        stmt = stmt.with_for_update(of=[User, ClinicMembership])
    row = db.execute(stmt).first()
    if row is None:
        raise NotFound("Membro não encontrado nesta clínica.")
    # Consulta separada, **depois** da trava: em READ COMMITTED ela enxerga o que quem
    # segurava a trava acabou de gravar (um EXISTS na mesma instrução usaria a foto antiga).
    other = db.scalar(select(_other_clinics_expr(clinic_id)).where(User.id == user_id))
    return Member(row[0], row[1], bool(other))


def _lock_active_admins(db: Session, clinic_id: uuid.UUID) -> list[uuid.UUID]:
    """Trava os vínculos de admin ativos da clínica e devolve os usuários.

    Duas mudanças concorrentes de admin esperam uma pela outra aqui, então a contagem
    de "sobra pelo menos um" não tem corrida. Quem pode mexer em admin chama isto
    **antes** de travar o membro alvo, e a ordem por id é fixa: sem deadlock entre elas.
    """
    return list(
        db.scalars(
            select(ClinicMembership.user_id)
            .join(User, User.id == ClinicMembership.user_id)
            .where(
                ClinicMembership.clinic_id == clinic_id,
                ClinicMembership.role == Role.ADMIN,
                ClinicMembership.active,
                User.active,
            )
            .order_by(ClinicMembership.id)
            .with_for_update(of=ClinicMembership)
        )
    )


def _is_active_admin(member: Member) -> bool:
    return member.membership.role is Role.ADMIN and member.membership.active and member.user.active


def _check_admin_remains(db: Session, clinic_id: uuid.UUID, leaving: uuid.UUID) -> None:
    if not [a for a in _lock_active_admins(db, clinic_id) if a != leaving]:
        raise RuleViolation("A clínica precisa ter pelo menos um administrador ativo.")


# --- Membros e convites ------------------------------------------------------------


def add_member(
    db: Session,
    actor: CurrentUser,
    *,
    email: str,
    full_name: str,
    cro: str | None,
    role: Role,
) -> Added:
    """E-mail novo: cria o usuário com senha aleatória. E-mail que já tem cadastro: cria
    um convite com código (nome e CRO informados são ignorados; os da pessoa não mudam)."""
    email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        password = generate_password()
        user = User(email=email, full_name=full_name, cro=cro, password_hash="")
        _set_password(user, password, temporary=True)
        db.add(user)
        db.flush()
        db.add(ClinicMembership(user_id=user.id, clinic_id=actor.clinic_id, role=role))
        db.flush()
        return Added(member=get_member(db, actor.clinic_id, user.id), password=password)

    member_id = db.scalar(
        select(ClinicMembership.id).where(
            ClinicMembership.clinic_id == actor.clinic_id, ClinicMembership.user_id == user.id
        )
    )
    if member_id is not None:
        raise RuleViolation(
            "Esta pessoa já faz parte da equipe. Se o acesso foi desativado, reative-o."
        )
    invite_id = db.scalar(
        select(MembershipInvite.id).where(
            MembershipInvite.clinic_id == actor.clinic_id, MembershipInvite.user_id == user.id
        )
    )
    if invite_id is not None:
        raise RuleViolation("Já existe um convite para este e-mail. Gere um código novo nele.")
    code = generate_code()
    invite = MembershipInvite(
        user_id=user.id,
        clinic_id=actor.clinic_id,
        role=role,
        code_hash=hash_password(code),
        expires_at=_now() + INVITE_TTL,
        created_by=actor.user_id,
    )
    db.add(invite)
    db.flush()
    return Added(invite=invite, code=code)


def list_invites(db: Session, clinic_id: uuid.UUID) -> list[tuple[MembershipInvite, str]]:
    """Convites da clínica com o e-mail convidado (sem nome nem CRO: a pessoa ainda não
    aceitou fazer parte da equipe)."""
    rows = db.execute(
        select(MembershipInvite, User.email)
        .join(User, User.id == MembershipInvite.user_id)
        .where(MembershipInvite.clinic_id == clinic_id)
        .order_by(MembershipInvite.created_at.desc())
    ).all()
    return [(i, e) for i, e in rows]


def _get_invite(db: Session, clinic_id: uuid.UUID, invite_id: uuid.UUID) -> MembershipInvite:
    invite = db.scalar(
        select(MembershipInvite)
        .where(MembershipInvite.id == invite_id, MembershipInvite.clinic_id == clinic_id)
        .with_for_update()
    )
    if invite is None:
        raise NotFound("Convite não encontrado.")
    return invite


def renew_invite(db: Session, actor: CurrentUser, invite_id: uuid.UUID) -> tuple[str, str]:
    """Novo código (o anterior deixa de valer) e mais 7 dias. Devolve (código, e-mail)."""
    invite = _get_invite(db, actor.clinic_id, invite_id)
    code = generate_code()
    invite.code_hash = hash_password(code)
    invite.expires_at = _now() + INVITE_TTL
    db.flush()
    email = db.scalar(select(User.email).where(User.id == invite.user_id))
    return code, email or ""


def cancel_invite(db: Session, actor: CurrentUser, invite_id: uuid.UUID) -> MembershipInvite:
    invite = _get_invite(db, actor.clinic_id, invite_id)
    db.delete(invite)
    db.flush()
    return invite


def accept_invite(db: Session, email: str, password: str, code: str) -> MembershipInvite:
    """A própria pessoa (e-mail e senha dela) aceita o convite com o código recebido.

    Sessão global: ainda não há clínica. Só olha os convites desse usuário.
    """
    user = verify_credentials(db, email, password, lock=True)
    if user.must_change_password:
        raise PasswordChangeRequired
    invites = db.scalars(
        select(MembershipInvite)
        .join(Clinic, Clinic.id == MembershipInvite.clinic_id)
        .where(
            MembershipInvite.user_id == user.id,
            MembershipInvite.expires_at > _now(),
            Clinic.active,
        )
        .order_by(MembershipInvite.id)
        .with_for_update(of=MembershipInvite)
    ).all()
    normalized = _normalize_code(code)
    for invite in invites:
        if verify_password(normalized, invite.code_hash):
            db.add(ClinicMembership(user_id=user.id, clinic_id=invite.clinic_id, role=invite.role))
            db.execute(delete(MembershipInvite).where(MembershipInvite.id == invite.id))
            db.flush()
            return invite
    raise InvalidCode("Código inválido ou vencido.")


def update_member(
    db: Session,
    actor: CurrentUser,
    user_id: uuid.UUID,
    *,
    fields: set[str],
    full_name: str | None = None,
    cro: str | None = None,
    role: Role | None = None,
    active: bool | None = None,
) -> tuple[Member, dict[str, object]]:
    """Aplica os campos informados (`fields`). Devolve o membro e o que mudou (para a
    auditoria: papel e ativo com antes/depois; nome e CRO só o nome do campo)."""
    _lock_active_admins(db, actor.clinic_id)
    member = get_member(db, actor.clinic_id, user_id, lock=True)
    m, user = member.membership, member.user
    changes: dict[str, object] = {}

    personal = {f for f in ("full_name", "cro") if f in fields}
    if personal:
        if _is_active_admin(member) and user_id != actor.user_id:
            raise RuleViolation("Nome e CRO de outro administrador só ele mesmo altera.")
        if member.other_clinics:
            raise RuleViolation(
                "Esta pessoa também atua em outra clínica: nome e CRO são dela e não são "
                "alterados por aqui."
            )
        if "full_name" in fields and full_name is not None and full_name != user.full_name:
            user.full_name = full_name
            changes["full_name"] = True
        if "cro" in fields and cro != user.cro:
            user.cro = cro
            changes["cro"] = True

    new_role = role if "role" in fields and role is not None else m.role
    new_active = active if "active" in fields and active is not None else m.active
    if (new_role, new_active) != (m.role, m.active):
        loses_admin = _is_active_admin(member) and (new_role is not Role.ADMIN or not new_active)
        if loses_admin:
            if user_id != actor.user_id:
                raise RuleViolation(
                    "Para rebaixar ou desativar outro administrador, faça um pedido: ele só "
                    "vale quando o próprio administrador aceitar."
                )
            _check_admin_remains(db, actor.clinic_id, leaving=user_id)
        if new_role != m.role:
            changes["role"] = {"de": m.role.value, "para": new_role.value}
            m.role = new_role
        if new_active != m.active:
            changes["active"] = {"de": m.active, "para": new_active}
            m.active = new_active
    db.flush()
    return member, changes


def reset_password(db: Session, actor: CurrentUser, user_id: uuid.UUID) -> str:
    _lock_active_admins(db, actor.clinic_id)  # mesma ordem de travas das outras mudanças
    member = get_member(db, actor.clinic_id, user_id, lock=True)
    if user_id == actor.user_id:
        raise RuleViolation("Para a sua própria senha, use a troca de senha.")
    if member.other_clinics:
        raise RuleViolation(
            "Esta pessoa também atua em outra clínica: a senha é dela e não é redefinida por aqui."
        )
    if member.membership.role is Role.ADMIN:
        raise RuleViolation("A senha de outro administrador não é redefinida por aqui.")
    password = generate_password()
    _set_password(member.user, password, temporary=True)
    db.flush()
    return password


def change_own_password(db: Session, user_id: uuid.UUID, current: str, new: str) -> None:
    user = db.get(User, user_id, with_for_update=True)
    if user is None or not verify_password(current, user.password_hash):
        raise Forbidden("Senha atual incorreta.")
    if current == new:
        raise RuleViolation("A nova senha precisa ser diferente da atual.")
    _set_password(user, new, temporary=False)
    db.flush()


def first_access(db: Session, email: str, current: str, new: str) -> User:
    """Troca a senha aleatória pela da pessoa, antes de entrar (sessão global).

    Só para quem está com senha provisória; para os outros, a resposta é a mesma de
    credencial errada (a troca normal exige estar logado: `POST /auth/senha`).
    """
    user = verify_credentials(db, email, current, lock=True)
    if not user.must_change_password:
        raise InvalidCredentials
    if current == new:
        raise RuleViolation("A nova senha precisa ser diferente da atual.")
    _set_password(user, new, temporary=False)
    db.flush()
    return user


# --- Pedidos de mudança de administrador -------------------------------------------


def expires_at(req: AdminChangeRequest) -> datetime:
    return req.created_at + REQUEST_TTL


def _expire_stale(db: Session, now: datetime) -> None:
    """Fecha as pendentes vencidas (o RLS limita à clínica da sessão)."""
    stale = db.scalars(
        select(AdminChangeRequest)
        .where(
            AdminChangeRequest.status == AdminChangeStatus.PENDENTE,
            AdminChangeRequest.created_at <= now - REQUEST_TTL,
        )
        .order_by(AdminChangeRequest.id)
        .with_for_update()
    ).all()
    for req in stale:
        req.status = AdminChangeStatus.EXPIRADA
        req.decided_at = now
    if stale:
        db.flush()


def list_requests(db: Session, *, only_pending: bool) -> list[AdminChangeRequest]:
    _expire_stale(db, _now())
    stmt = select(AdminChangeRequest).order_by(AdminChangeRequest.created_at.desc())
    if only_pending:
        stmt = stmt.where(AdminChangeRequest.status == AdminChangeStatus.PENDENTE)
    else:
        stmt = stmt.limit(100)
    return list(db.scalars(stmt))


def get_request(db: Session, request_id: uuid.UUID) -> AdminChangeRequest:
    req = db.get(AdminChangeRequest, request_id, with_for_update=True)
    if req is None:  # de outra clínica, o RLS esconde
        raise NotFound("Pedido não encontrado.")
    return req


def create_request(
    db: Session,
    actor: CurrentUser,
    *,
    user_id: uuid.UUID,
    action: AdminChangeAction,
    new_role: Role | None,
    reason: str | None,
) -> AdminChangeRequest:
    if user_id == actor.user_id:
        raise RuleViolation("Para mudar o seu próprio acesso, altere direto no seu cadastro.")
    _lock_active_admins(db, actor.clinic_id)  # mesma ordem de travas das outras mudanças
    member = get_member(db, actor.clinic_id, user_id, lock=True)
    if not _is_active_admin(member):
        raise RuleViolation("Só se faz pedido para mudar um administrador ativo.")
    _expire_stale(db, _now())
    pending = db.scalar(
        select(AdminChangeRequest.id).where(
            AdminChangeRequest.target_user_id == user_id,
            AdminChangeRequest.status == AdminChangeStatus.PENDENTE,
        )
    )
    if pending is not None:
        raise RuleViolation("Já existe um pedido pendente para este administrador.")
    req = AdminChangeRequest(
        clinic_id=actor.clinic_id,
        target_user_id=user_id,
        action=action,
        new_role=new_role,
        reason=reason,
        requested_by=actor.user_id,
    )
    db.add(req)
    db.flush()
    db.refresh(req)  # created_at do servidor, para calcular a validade
    return req


def _require_pending(req: AdminChangeRequest, now: datetime) -> None:
    if req.status is not AdminChangeStatus.PENDENTE:
        raise RuleViolation("Este pedido já foi encerrado.")
    if now >= expires_at(req):
        raise RuleViolation("Este pedido expirou. Faça um novo, se ainda for preciso.")


def accept_request(db: Session, actor: CurrentUser, req: AdminChangeRequest) -> Member:
    """O próprio administrador alvo aceita o pedido, e a mudança é aplicada."""
    now = _now()
    _require_pending(req, now)
    if req.target_user_id != actor.user_id:
        raise Forbidden("Só o próprio administrador pode aceitar este pedido.")
    _lock_active_admins(db, actor.clinic_id)
    requester = get_member(db, actor.clinic_id, req.requested_by)
    if not _is_active_admin(requester):
        raise RuleViolation("Quem pediu não é mais administrador. Recuse este pedido.")
    target = get_member(db, actor.clinic_id, req.target_user_id, lock=True)
    if not _is_active_admin(target):
        raise RuleViolation("Você já não é administrador ativo. Recuse este pedido.")
    _check_admin_remains(db, actor.clinic_id, leaving=req.target_user_id)

    if req.action is AdminChangeAction.REBAIXAR:
        assert req.new_role is not None  # noqa: S101 - garantido pelo CHECK da migração
        target.membership.role = req.new_role
    else:
        target.membership.active = False
    req.status = AdminChangeStatus.APROVADA
    req.decided_by = actor.user_id
    req.decided_at = now
    db.flush()
    return target


def reject_request(db: Session, actor: CurrentUser, req: AdminChangeRequest) -> None:
    now = _now()
    _require_pending(req, now)
    if req.target_user_id != actor.user_id:
        raise Forbidden("Só o próprio administrador pode recusar este pedido.")
    req.status = AdminChangeStatus.RECUSADA
    req.decided_by = actor.user_id
    req.decided_at = now
    db.flush()


def cancel_request(db: Session, actor: CurrentUser, req: AdminChangeRequest) -> None:
    if req.status is not AdminChangeStatus.PENDENTE:
        raise RuleViolation("Este pedido já foi encerrado.")
    if req.requested_by != actor.user_id:
        raise Forbidden("Só quem pediu cancela o pedido.")
    req.status = AdminChangeStatus.CANCELADA
    req.decided_by = actor.user_id
    req.decided_at = _now()
    db.flush()


def names(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Nomes dos envolvidos em pedidos da clínica (ids vindos de linhas isoladas por RLS)."""
    if not user_ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all())
