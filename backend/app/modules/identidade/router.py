from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.db import get_db, tenant_session
from app.core.security import create_access_token
from app.modules.identidade import service
from app.modules.identidade.deps import get_current_user
from app.modules.identidade.models import Clinic, User
from app.modules.identidade.schemas import (
    ClinicOption,
    ClinicSelectionResponse,
    LoginRequest,
    MeResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["autenticação"])


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={409: {"model": ClinicSelectionResponse}},
)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        result = service.authenticate(db, body.email, body.password, body.clinic_id)
    except service.InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos"
        ) from None
    except service.ClinicSelectionRequired as exc:
        payload = ClinicSelectionResponse(
            clinics=[ClinicOption(id=c.id, name=c.name) for c in exc.clinics]
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content=payload.model_dump(mode="json")
        )

    user = CurrentUser(user_id=result.user.id, clinic_id=result.clinic.id, role=result.role)
    with tenant_session(result.clinic.id) as tdb:
        audit.record(tdb, user, "auth.login", request=request)
        tdb.commit()

    minutes = get_settings().access_token_minutes
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.clinic_id, user.role),
        expires_in=minutes * 60,
        clinic=ClinicOption(id=result.clinic.id, name=result.clinic.name),
        role=result.role,
    )


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
