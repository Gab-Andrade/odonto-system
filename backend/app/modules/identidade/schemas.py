import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

from app.core.roles import Role
from app.modules.identidade.models import AdminChangeAction, AdminChangeStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    clinic_id: uuid.UUID | None = None  # obrigatório se o usuário atua em mais de uma clínica


class ClinicOption(BaseModel):
    id: uuid.UUID
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    clinic: ClinicOption
    role: Role


class ClinicSelectionResponse(BaseModel):
    detail: str = "Selecione a clínica"
    clinics: list[ClinicOption]


class MeResponse(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    cro: str | None
    clinic: ClinicOption
    role: Role


class TeamMember(BaseModel):
    user_id: uuid.UUID
    full_name: str
    role: Role
    cro: str | None


# --- Cadastro de equipe (só admin) -------------------------------------------------

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Cro = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
NewPassword = Annotated[str, Field(min_length=10, max_length=200)]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    cro: str | None
    role: Role
    active: bool = Field(description="Vínculo ativo nesta clínica.")
    other_clinics: bool = Field(
        description="A pessoa também tem vínculo em outra clínica: nome, CRO e senha são "
        "dela e não são alterados por aqui."
    )
    since: datetime = Field(description="Quando o vínculo com esta clínica foi criado.")


class MemberCreate(BaseModel):
    email: EmailStr
    full_name: Name
    cro: Cro | None = None
    role: Role


class InviteOut(BaseModel):
    """Convite a um e-mail que já tem cadastro (sem nome nem CRO até a pessoa aceitar)."""

    id: uuid.UUID
    email: str
    role: Role
    expires_at: datetime
    created_at: datetime


class MemberCreated(BaseModel):
    """E-mail novo: `member` + `temporary_password`. E-mail que já tem cadastro: `invite`
    + `invite_code`, que a clínica entrega à pessoa; o vínculo só vale depois que ela o
    digitar. Senha e código aparecem só nesta resposta."""

    member: MemberOut | None = None
    temporary_password: str | None = None
    invite: InviteOut | None = None
    invite_code: str | None = None


class InviteCode(BaseModel):
    invite_code: str
    email: str


class InviteAccept(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=40)


class FirstAccess(BaseModel):
    """Troca a senha aleatória e entra (mesma resposta do login)."""

    email: EmailStr
    current_password: str = Field(min_length=1, max_length=200)
    new_password: Annotated[str, Field(min_length=10, max_length=200)]
    clinic_id: uuid.UUID | None = None


class MemberUpdate(BaseModel):
    """Campos omitidos não mudam. `cro: null` apaga o CRO."""

    full_name: Name | None = None
    cro: Cro | None = None
    role: Role | None = None
    active: bool | None = None


class TemporaryPassword(BaseModel):
    temporary_password: str


class AdminChangeCreate(BaseModel):
    user_id: uuid.UUID
    action: AdminChangeAction
    new_role: Role | None = None
    reason: Reason | None = None

    @model_validator(mode="after")
    def _role_matches_action(self):
        if self.action is AdminChangeAction.REBAIXAR:
            if self.new_role is None or self.new_role is Role.ADMIN:
                raise ValueError("Rebaixar pede o papel novo, diferente de admin.")
        elif self.new_role is not None:
            raise ValueError("Desativar não leva papel novo.")
        return self


class AdminChangeOut(BaseModel):
    id: uuid.UUID
    target_user_id: uuid.UUID
    target_name: str
    action: AdminChangeAction
    new_role: Role | None
    reason: str | None
    requested_by: uuid.UUID
    requested_by_name: str
    status: AdminChangeStatus
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    expires_at: datetime


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: NewPassword
