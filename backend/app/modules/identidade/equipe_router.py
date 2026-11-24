"""Cadastro de equipe: só administrador da clínica (o aceite de convite e o primeiro acesso
ficam em `router.py`, porque acontecem antes de haver clínica na sessão).

Usuários e vínculos são globais; o service filtra por clínica de forma explícita. A sessão
é a de tenant, para gravar a auditoria e as solicitações (RLS) na mesma transação.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade import equipe_service as service
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.identidade.models import AdminChangeRequest, MembershipInvite
from app.modules.identidade.schemas import (
    AdminChangeCreate,
    AdminChangeOut,
    InviteCode,
    InviteOut,
    MemberCreate,
    MemberCreated,
    MemberOut,
    MemberUpdate,
    TemporaryPassword,
)

router = APIRouter(prefix="/equipe", tags=["equipe"])

_admin = require_roles(Role.ADMIN)
ENTITY = "usuario"


def _http(exc: service.TeamError) -> HTTPException:
    if isinstance(exc, service.NotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, service.Forbidden):
        code = status.HTTP_403_FORBIDDEN
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=exc.message)


def _invite_out(i: MembershipInvite, email: str) -> InviteOut:
    return InviteOut(
        id=i.id, email=email, role=i.role, expires_at=i.expires_at, created_at=i.created_at
    )


def _member_out(m: service.Member) -> MemberOut:
    return MemberOut(
        user_id=m.user.id,
        full_name=m.user.full_name,
        email=m.user.email,
        cro=m.user.cro,
        role=m.membership.role,
        active=m.membership.active and m.user.active,
        other_clinics=m.other_clinics,
        since=m.membership.created_at,
    )


def _requests_out(db: Session, reqs: list[AdminChangeRequest]) -> list[AdminChangeOut]:
    who = service.names(db, {r.target_user_id for r in reqs} | {r.requested_by for r in reqs})
    return [
        AdminChangeOut(
            id=r.id,
            target_user_id=r.target_user_id,
            target_name=who.get(r.target_user_id, "—"),
            action=r.action,
            new_role=r.new_role,
            reason=r.reason,
            requested_by=r.requested_by,
            requested_by_name=who.get(r.requested_by, "—"),
            status=r.status,
            decided_by=r.decided_by,
            decided_at=r.decided_at,
            created_at=r.created_at,
            expires_at=service.expires_at(r),
        )
        for r in reqs
    ]


@router.get("/membros", response_model=list[MemberOut])
def list_members(
    incluir_inativos: bool = Query(False),
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Equipe da clínica com e-mail e situação do acesso (a lista para todos os papéis,
    sem e-mail, é `GET /auth/equipe`)."""
    return [
        _member_out(m)
        for m in service.list_members(db, user.clinic_id, include_inactive=incluir_inativos)
    ]


@router.post("/membros", response_model=MemberCreated, status_code=status.HTTP_201_CREATED)
def add_member(
    body: MemberCreate,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Adiciona alguém à equipe. E-mail novo: cria o usuário com senha aleatória (ele define
    a dele no primeiro acesso). E-mail que já tem cadastro: cria um convite com código, que
    a clínica entrega à pessoa; o vínculo só vale depois que ela digitar o código."""
    try:
        added = service.add_member(
            db, user, email=body.email, full_name=body.full_name, cro=body.cro, role=body.role
        )
    except service.TeamError as exc:
        raise _http(exc) from None
    if added.member is not None:
        audit.record(
            db,
            user,
            "equipe.membro_adicionado",
            entity_type=ENTITY,
            entity_id=added.member.user.id,
            details={"papel": added.member.membership.role.value},
            request=request,
        )
        out = MemberCreated(member=_member_out(added.member), temporary_password=added.password)
    else:
        assert added.invite is not None  # noqa: S101
        audit.record(
            db,
            user,
            "equipe.convite_criado",
            entity_type=ENTITY,
            entity_id=added.invite.user_id,
            details={"papel": added.invite.role.value},
            request=request,
        )
        out = MemberCreated(
            invite=_invite_out(added.invite, service.normalize_email(body.email)),
            invite_code=added.code,
        )
    db.commit()
    response.headers["Cache-Control"] = "no-store"  # traz senha ou código
    return out


@router.get("/convites", response_model=list[InviteOut])
def list_invites(user: CurrentUser = Depends(_admin), db: Session = Depends(get_tenant_db)):
    """Convites ainda não aceitos (vencidos aparecem até gerar código novo ou cancelar)."""
    return [_invite_out(i, email) for i, email in service.list_invites(db, user.clinic_id)]


@router.post("/convites/{invite_id}/novo-codigo", response_model=InviteCode)
def renew_invite(
    invite_id: uuid.UUID,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Gera outro código (o anterior deixa de valer) e renova o prazo de 7 dias."""
    try:
        code, email = service.renew_invite(db, user, invite_id)
    except service.TeamError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "equipe.convite_renovado", entity_type="convite", entity_id=invite_id,
        request=request,
    )  # fmt: skip
    db.commit()
    response.headers["Cache-Control"] = "no-store"  # traz código
    return InviteCode(invite_code=code, email=email)


@router.delete("/convites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invite(
    invite_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    try:
        invite = service.cancel_invite(db, user, invite_id)
    except service.TeamError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "equipe.convite_cancelado", entity_type=ENTITY, entity_id=invite.user_id,
        request=request,
    )  # fmt: skip
    db.commit()


@router.patch("/membros/{user_id}", response_model=MemberOut)
def update_member(
    user_id: uuid.UUID,
    body: MemberUpdate,
    request: Request,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Muda papel, ativa/desativa o acesso nesta clínica e corrige nome e CRO. Rebaixar ou
    desativar outro administrador não é feito aqui: use `POST /equipe/solicitacoes`."""
    try:
        member, changes = service.update_member(
            db,
            user,
            user_id,
            fields=body.model_fields_set,
            full_name=body.full_name,
            cro=body.cro,
            role=body.role,
            active=body.active,
        )
    except service.TeamError as exc:
        raise _http(exc) from None
    if changes:
        audit.record(
            db,
            user,
            "equipe.membro_alterado",
            entity_type=ENTITY,
            entity_id=user_id,
            details=changes,
            request=request,
        )
    db.commit()
    return _member_out(member)


@router.post("/membros/{user_id}/redefinir-senha", response_model=TemporaryPassword)
def reset_password(
    user_id: uuid.UUID,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Gera uma senha aleatória nova (mostrada só nesta resposta). Não vale para outro
    administrador nem para quem também atua em outra clínica."""
    try:
        password = service.reset_password(db, user, user_id)
    except service.TeamError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "equipe.senha_redefinida", entity_type=ENTITY, entity_id=user_id, request=request
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"  # traz senha
    return TemporaryPassword(temporary_password=password)


@router.get("/solicitacoes", response_model=list[AdminChangeOut])
def list_requests(
    somente_pendentes: bool = Query(True),
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Pedidos para rebaixar ou desativar administrador (sem filtro: os 100 mais
    recentes)."""
    reqs = service.list_requests(db, only_pending=somente_pendentes)
    out = _requests_out(db, reqs)
    db.commit()  # grava as que expiraram
    return out


@router.post("/solicitacoes", response_model=AdminChangeOut, status_code=status.HTTP_201_CREATED)
def create_request(
    body: AdminChangeCreate,
    request: Request,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Pede para rebaixar ou desativar outro administrador. Só vale quando o próprio
    administrador alvo aceitar; expira em 7 dias."""
    try:
        req = service.create_request(
            db,
            user,
            user_id=body.user_id,
            action=body.action,
            new_role=body.new_role,
            reason=body.reason,
        )
    except service.TeamError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "equipe.solicitacao_criada",
        entity_type="solicitacao_admin",
        entity_id=req.id,
        details={
            "alvo": str(req.target_user_id),
            "acao": req.action.value,
            "papel_novo": req.new_role.value if req.new_role else None,
        },
        request=request,
    )
    out = _requests_out(db, [req])[0]
    db.commit()
    return out


def _decide(
    action: str,
    request_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: Session,
) -> AdminChangeOut:
    try:
        req = service.get_request(db, request_id)
        details: dict[str, object] = {"alvo": str(req.target_user_id)}
        if action == "aceita":
            service.accept_request(db, user, req)
            details["acao"] = req.action.value
            details["papel_novo"] = req.new_role.value if req.new_role else None
        elif action == "recusada":
            service.reject_request(db, user, req)
        else:
            service.cancel_request(db, user, req)
    except service.TeamError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        f"equipe.solicitacao_{action}",
        entity_type="solicitacao_admin",
        entity_id=req.id,
        details=details,
        request=request,
    )
    out = _requests_out(db, [req])[0]
    db.commit()
    return out


@router.post("/solicitacoes/{request_id}/aceitar", response_model=AdminChangeOut)
def accept_request(
    request_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """O próprio administrador alvo aceita o pedido, e a mudança é aplicada."""
    return _decide("aceita", request_id, request, user, db)


@router.post("/solicitacoes/{request_id}/recusar", response_model=AdminChangeOut)
def reject_request(
    request_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    return _decide("recusada", request_id, request, user, db)


@router.post("/solicitacoes/{request_id}/cancelar", response_model=AdminChangeOut)
def cancel_request(
    request_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(_admin),
    db: Session = Depends(get_tenant_db),
):
    """Quem pediu desiste do pedido."""
    return _decide("cancelada", request_id, request, user, db)
