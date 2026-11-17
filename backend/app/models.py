"""Importa todos os models para que o metadata fique completo (Alembic, testes).

Ao criar um módulo novo com models.py, adicione o import aqui.
"""

from app.core.audit import AuditLog
from app.core.models import Base
from app.modules.identidade.models import Clinic, ClinicMembership, User
from app.modules.precificacao.models import (
    ImportJob,
    ImportProfile,
    PriceAssignment,
    PriceItem,
    PriceSnapshot,
    PriceTable,
    PriceTableVersion,
)

__all__ = [
    "AuditLog",
    "Base",
    "Clinic",
    "ClinicMembership",
    "ImportJob",
    "ImportProfile",
    "PriceAssignment",
    "PriceItem",
    "PriceSnapshot",
    "PriceTable",
    "PriceTableVersion",
    "User",
]
