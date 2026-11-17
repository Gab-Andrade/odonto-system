import uuid

from pydantic import BaseModel, EmailStr, Field

from app.core.roles import Role


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
