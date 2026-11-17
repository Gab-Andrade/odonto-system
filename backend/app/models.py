"""Importa todos os models para que o metadata fique completo (Alembic, testes).

Ao criar um módulo novo com models.py, adicione o import aqui.
"""

from app.core.audit import AuditLog
from app.core.models import Base
from app.modules.estoque.models import Material
from app.modules.identidade.models import Clinic, ClinicMembership, User
from app.modules.precificacao.models import (
    CostSheet,
    CostSheetItem,
    ImportJob,
    ImportProfile,
    PriceAssignment,
    PriceItem,
    PriceSnapshot,
    PriceTable,
    PriceTableVersion,
    PricingVariable,
)

__all__ = [
    "AuditLog",
    "Base",
    "Clinic",
    "ClinicMembership",
    "CostSheet",
    "CostSheetItem",
    "ImportJob",
    "ImportProfile",
    "Material",
    "PriceAssignment",
    "PriceItem",
    "PriceSnapshot",
    "PriceTable",
    "PriceTableVersion",
    "PricingVariable",
    "User",
]
