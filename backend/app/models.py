"""Importa todos os models para que o metadata fique completo (Alembic, testes).

Ao criar um módulo novo com models.py, adicione o import aqui.
"""

from app.core.audit import AuditLog
from app.core.models import Base
from app.modules.agenda.models import Appointment, AppointmentEvent, Chair
from app.modules.estoque.models import Material
from app.modules.identidade.models import Clinic, ClinicMembership, User
from app.modules.odontograma.models import OdontogramEvent, ToothStatus
from app.modules.pacientes.models import Patient, PatientConsent
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
from app.modules.prontuario.models import (
    AnamnesisResponse,
    AnamnesisTemplate,
    AnamnesisTemplateVersion,
    ClinicalNote,
    ClinicalNoteSignature,
    Encounter,
)

__all__ = [
    "AnamnesisResponse",
    "AnamnesisTemplate",
    "AnamnesisTemplateVersion",
    "Appointment",
    "AppointmentEvent",
    "AuditLog",
    "Base",
    "Chair",
    "ClinicalNote",
    "ClinicalNoteSignature",
    "Clinic",
    "ClinicMembership",
    "CostSheet",
    "CostSheetItem",
    "Encounter",
    "ImportJob",
    "ImportProfile",
    "Material",
    "OdontogramEvent",
    "Patient",
    "PatientConsent",
    "PriceAssignment",
    "PriceItem",
    "PriceSnapshot",
    "PriceTable",
    "PriceTableVersion",
    "PricingVariable",
    "ToothStatus",
    "User",
]
