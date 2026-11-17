"""Regras do cadastro de pacientes. O commit e a auditoria ficam com o router."""

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.modules.pacientes import dados
from app.modules.pacientes.models import (
    ConsentGivenBy,
    ConsentPurpose,
    Patient,
    PatientConsent,
)

MAX_SEARCH_RESULTS = 100


class PatientError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(PatientError):
    pass


class RuleViolation(PatientError):
    pass


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


# ---------- Cadastro ----------


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:  # de outra clínica também cai aqui (RLS)
        raise NotFound("Paciente não encontrado.")
    return patient


def _ensure_cpf_free(db: Session, cpf: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(Patient.id).where(Patient.cpf == cpf)
    if exclude_id is not None:
        query = query.where(Patient.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise RuleViolation("Já existe paciente com este CPF na clínica.")


def _check(patient: Patient) -> None:
    """Regras que dependem de mais de um campo, conferidas depois de aplicar as mudanças."""
    if dados.is_minor(patient.birth_date, today()) and not patient.guardian_name:
        raise RuleViolation("Paciente menor de 18 anos precisa de um responsável.")
    if patient.cpf is not None and patient.cpf == patient.guardian_cpf:
        raise RuleViolation("O CPF do responsável não pode ser o do próprio paciente.")


def create_patient(db: Session, user: CurrentUser, data: dict[str, Any]) -> Patient:
    if data.get("cpf"):
        _ensure_cpf_free(db, data["cpf"])
    patient = Patient(clinic_id=user.clinic_id, created_by=user.user_id, **data)
    patient.search_name = dados.search_name(patient.full_name, patient.social_name)
    _check(patient)
    db.add(patient)
    db.flush()
    return patient


REQUIRED_FIELDS = ("full_name", "phone")


def update_patient(db: Session, patient: Patient, changes: dict[str, Any]) -> list[str]:
    """Aplica as mudanças e devolve os nomes dos campos que mudaram (para a auditoria)."""
    for name in REQUIRED_FIELDS + ("active",):
        if name in changes and changes[name] is None:
            raise RuleViolation(f"O campo {name} não pode ficar vazio.")
    if changes.get("cpf") and changes["cpf"] != patient.cpf:
        _ensure_cpf_free(db, changes["cpf"], exclude_id=patient.id)
    changed = [k for k, v in changes.items() if getattr(patient, k) != v]
    for key in changed:
        setattr(patient, key, changes[key])
    patient.search_name = dados.search_name(patient.full_name, patient.social_name)
    _check(patient)
    db.flush()
    return sorted(changed)


def search_patients(
    db: Session, term: str | None, *, include_inactive: bool, limit: int, offset: int
) -> list[Patient]:
    """Busca por trecho do nome (sem acento, todas as palavras) ou por dígitos de CPF/telefone.

    Um termo sem letras e com ao menos 4 dígitos é tratado como documento ou telefone.
    """
    query: Select[tuple[Patient]] = select(Patient)
    if not include_inactive:
        query = query.where(Patient.active)
    term = (term or "").strip()
    digits = dados.only_digits(term)
    if term and not any(c.isalpha() for c in term) and len(digits) >= 4:
        pattern = f"%{digits}%"
        query = query.where(
            or_(Patient.cpf == digits, Patient.phone.like(pattern), Patient.phone_alt.like(pattern))
        )
    elif term:
        for word in dados.normalize_text(term).split():
            query = query.where(
                Patient.search_name.like(f"%{dados.escape_like(word)}%", escape="\\")
            )
    query = query.order_by(Patient.search_name, Patient.id)
    return list(db.scalars(query.limit(min(limit, MAX_SEARCH_RESULTS)).offset(offset)))


# ---------- Consentimentos ----------


def list_consents(db: Session, patient: Patient) -> list[PatientConsent]:
    return list(
        db.scalars(
            select(PatientConsent)
            .where(PatientConsent.patient_id == patient.id)
            .order_by(PatientConsent.created_at.desc(), PatientConsent.id)
        )
    )


def current_consents(
    history: list[PatientConsent],
) -> dict[ConsentPurpose, PatientConsent | None]:
    """Estado atual por finalidade: o evento mais recente (o histórico vem do mais novo)."""
    current: dict[ConsentPurpose, PatientConsent | None] = dict.fromkeys(ConsentPurpose)
    for event in history:
        if current[event.purpose] is None:
            current[event.purpose] = event
    return current


def record_consent(
    db: Session, user: CurrentUser, patient: Patient, data: dict[str, Any]
) -> PatientConsent:
    by_guardian = data["given_by"] == ConsentGivenBy.RESPONSAVEL
    if by_guardian and not patient.guardian_name:
        raise RuleViolation("Cadastre o responsável do paciente antes.")
    if dados.is_minor(patient.birth_date, today()) and not by_guardian:
        raise RuleViolation("Paciente menor de idade: o consentimento é dado pelo responsável.")
    consent = PatientConsent(
        clinic_id=user.clinic_id, patient_id=patient.id, recorded_by=user.user_id, **data
    )
    db.add(consent)
    db.flush()
    return consent
