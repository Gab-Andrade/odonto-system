import uuid
from dataclasses import dataclass

from app.core.roles import Role


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    clinic_id: uuid.UUID
    role: Role
