from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.db import get_db, tenant_session
from app.core.security import create_access_token
from app.modules.identidade import equipe_service, service
from app.modules.identidade.deps import get_current_user, get_tenant_db
from app.modules.identidade.models import Clinic, User
from app.modules.identidade.schemas import (
    ClinicOption,
    ClinicSelectionResponse,
    FirstAccess,
    InviteAccept,
    LoginRequest,
    MeResponse,
    PasswordChange,
    TeamMember,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["autenticação"])

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos"
)
_MUST_CHANGE = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Defina uma senha sua para continuar.",
)


def _token(user: CurrentUser, clinic_name: str) -> TokenResponse:
    minutes = get_settings().access_token_minutes
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.clinic_id, user.role),
        expires_in=minutes * 60,
        clinic=ClinicOption(id=user.clinic_id, name=clinic_name),
        role=user.role,
    )


def _sign_in(
    db: Session,
    request: Request,
    email: str,
    password: str,
    clinic_id,
    *,
    action: str = "auth.login",
) -> TokenResponse | JSONResponse:
    """Autentica, audita e devolve o token (ou o 409 de escolha de clínica)."""
    try:
        result = service.authenticate(db, email, password, clinic_id)
    except service.InvalidCredentials:
        raise _INVALID from None
    except service.PasswordChangeRequired:
        raise _MUST_CHANGE from None
    except service.ClinicSelectionRequired as exc:
        payload = ClinicSelectionResponse(
            clinics=[ClinicOption(id=c.id, name=c.name) for c in exc.clinics]
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content=payload.model_dump(mode="json")
        )

    user = CurrentUser(user_id=result.user.id, clinic_id=result.clinic.id, role=result.role)
    with tenant_session(result.clinic.id) as tdb:
        audit.record(tdb, user, action, request=request)
        tdb.commit()
    return _token(user, result.clinic.name)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        403: {"description": "Senha aleatória: defina a sua em `POST /auth/primeiro-acesso`."},
        409: {"model": ClinicSelectionResponse},
    },
)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return _sign_in(db, request, body.email, body.password, body.clinic_id)


@router.post(
    "/primeiro-acesso",
    response_model=TokenResponse,
    responses={409: {"model": ClinicSelectionResponse}},
)
def first_access(body: FirstAccess, request: Request, db: Session = Depends(get_db)):
    """Troca a senha aleatória (do cadastro ou de uma redefinição) pela da pessoa e entra.
    Se ela atua em mais de uma clínica, responde 409 como o login: a senha já foi trocada,
    e o login segue com a senha nova e a clínica escolhida."""
    try:
        user = equipe_service.first_access(db, body.email, body.current_password, body.new_password)
    except service.InvalidCredentials:
        raise _INVALID from None
    except equipe_service.TeamError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from None
    db.commit()
    # A senha é da pessoa: a troca fica registrada em todas as clínicas em que ela atua.
    for clinic_id, role in service.active_memberships(db, user.id):
        actor = CurrentUser(user_id=user.id, clinic_id=clinic_id, role=role)
        with tenant_session(clinic_id) as tdb:
            audit.record(tdb, actor, "auth.senha_definida", entity_type="usuario",
                         entity_id=user.id, request=request)  # fmt: skip
            tdb.commit()
    return _sign_in(db, request, body.email, body.new_password, body.clinic_id)


@router.post("/vinculos/aceitar", status_code=status.HTTP_204_NO_CONTENT)
def accept_invite(body: InviteAccept, request: Request, db: Session = Depends(get_db)):
    """A pessoa aceita o convite de uma clínica com o código que recebeu dela, usando o
    e-mail e a senha que já tem. Depois, entra normalmente escolhendo a clínica."""
    try:
        invite = equipe_service.accept_invite(db, body.email, body.password, body.code)
    except service.InvalidCredentials:
        raise _INVALID from None
    except service.PasswordChangeRequired:
        raise _MUST_CHANGE from None
    except equipe_service.InvalidCode as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from None
    db.commit()
    user = CurrentUser(user_id=invite.user_id, clinic_id=invite.clinic_id, role=invite.role)
    with tenant_session(invite.clinic_id) as tdb:
        audit.record(
            tdb,
            user,
            "equipe.convite_aceito",
            entity_type="usuario",
            entity_id=invite.user_id,
            details={"papel": invite.role.value},
            request=request,
        )
        tdb.commit()


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db_user = db.get(User, user.user_id)
    clinic = db.get(Clinic, user.clinic_id)
    if db_user is None or clinic is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado")
    return MeResponse(
        user_id=db_user.id,
        full_name=db_user.full_name,
        email=db_user.email,
        cro=db_user.cro,
        clinic=ClinicOption(id=clinic.id, name=clinic.name),
        role=user.role,
    )


@router.get("/equipe", response_model=list[TeamMember])
def team(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Nome e papel dos membros ativos da clínica (para escolher dentista na agenda, no
    plano etc.). Sem e-mail: só o que aparece nas telas."""
    return [
        TeamMember(user_id=u.id, full_name=u.full_name, role=role, cro=u.cro)
        for u, role in service.team(db, user.clinic_id)
    ]


@router.post("/senha", response_model=TokenResponse)
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    """Troca a própria senha (vale em todas as clínicas da pessoa). As sessões abertas
    com a senha antiga caem; a resposta traz um token novo para esta."""
    try:
        equipe_service.change_own_password(
            db, user.user_id, body.current_password, body.new_password
        )
    except equipe_service.TeamError as exc:
        code = 403 if isinstance(exc, equipe_service.Forbidden) else 409
        raise HTTPException(status_code=code, detail=exc.message) from None
    audit.record(db, user, "auth.senha_trocada", entity_type="usuario", entity_id=user.user_id,
                 request=request)  # fmt: skip
    clinic_name = db.get(Clinic, user.clinic_id).name
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return _token(user, clinic_name)
