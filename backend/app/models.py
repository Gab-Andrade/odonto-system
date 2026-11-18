"""Importa todos os models para que o metadata fique completo (Alembic, testes).

Ao criar um módulo novo com models.py, adicione o import aqui.
"""

from app.core.audit import AuditLog
from app.core.models import Base
from app.modules.agenda.models import Appointment, AppointmentEvent, Chair
from app.modules.estoque.models import Material, StockLot, StockMovement
from app.modules.financeiro.models import FinancialSettings, Payable, Payment, Receivable
from app.modules.identidade.models import Clinic, ClinicMembership, User
from app.modules.imagens.models import ImagingExam
from app.modules.inteligencia.models import AlertDismissal, AlertRuleSetting
from app.modules.odontograma.models import (
    ArchConfig,
    OdontogramEvent,
    PersonalColor,
    ToothNote,
    ToothStatus,
)
from app.modules.pacientes.models import Patient, PatientConsent
from app.modules.painel.models import PanelGoal
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
    EncounterTransfer,
)
from app.modules.repasse.models import CommissionLine, CommissionRule, CommissionSettlement
from app.modules.tratamento.models import (
    TreatmentPlan,
    TreatmentPlanItem,
    TreatmentSettings,
)

__all__ = [
    "AlertDismissal",
    "AlertRuleSetting",
    "AnamnesisResponse",
    "AnamnesisTemplate",
    "AnamnesisTemplateVersion",
    "ArchConfig",
    "Appointment",
    "AppointmentEvent",
    "AuditLog",
    "Base",
    "Chair",
    "ClinicalNote",
    "ClinicalNoteSignature",
    "Clinic",
    "CommissionLine",
    "CommissionRule",
    "CommissionSettlement",
    "ClinicMembership",
    "CostSheet",
    "CostSheetItem",
    "Encounter",
    "EncounterTransfer",
    "FinancialSettings",
    "ImagingExam",
    "ImportJob",
    "ImportProfile",
    "Material",
    "OdontogramEvent",
    "PanelGoal",
    "Patient",
    "PatientConsent",
    "Payable",
    "Payment",
    "PersonalColor",
    "PriceAssignment",
    "PriceItem",
    "PriceSnapshot",
    "PriceTable",
    "PriceTableVersion",
    "PricingVariable",
    "Receivable",
    "StockLot",
    "StockMovement",
    "ToothNote",
    "ToothStatus",
    "TreatmentPlan",
    "TreatmentPlanItem",
    "TreatmentSettings",
    "User",
]
