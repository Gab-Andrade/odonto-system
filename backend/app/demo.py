"""Dados de demonstração para testar o sistema localmente (`python -m app.cli demo`).

Idempotente: o que já existe (usuários, cadeira, tabela, pacientes pelo nome) é mantido e
não é duplicado. Tudo passa pelos services, então as regras de negócio valem como na API.
Recusado com ENVIRONMENT=production.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.db import get_sessionmaker, tenant_session
from app.core.roles import Role
from app.core.security import hash_password
from app.modules.agenda import service as agenda
from app.modules.agenda.models import Appointment, Chair
from app.modules.identidade.models import Clinic, ClinicMembership, User
from app.modules.identidade.service import create_clinic_with_admin, normalize_email
from app.modules.odontograma import service as odontograma
from app.modules.odontograma.models import ToothStatus
from app.modules.pacientes import service as pacientes
from app.modules.pacientes.models import ConsentGivenBy, ConsentPurpose, Patient, Sex
from app.modules.precificacao import service as pricing
from app.modules.precificacao.models import PriceAssignment, PriceTable, ScopeType
from app.modules.tratamento import service as tratamento
from app.modules.tratamento.models import TreatmentPlan

DEMO_PASSWORD = "demo-odonto-2026"  # noqa: S105 - só para dados locais de demonstração
DEMO_TABLE = "Tabela Demo"
DEMO_CHAIR = "Cadeira Demo"

# Procedimentos da tabela de demonstração (código, descrição, categoria, preço).
PROCEDURES = (
    ("DEMO-PROF", "Profilaxia (limpeza)", "Prevenção", "180.00"),
    ("DEMO-REST", "Restauração em resina", "Dentística", "250.00"),
    ("DEMO-ENDO", "Tratamento de canal (molar)", "Endodontia", "1200.00"),
    ("DEMO-EXO", "Extração simples", "Cirurgia", "220.00"),
    ("DEMO-SEL", "Selante (por dente)", "Prevenção", "90.00"),
    ("DEMO-COROA", "Coroa em porcelana", "Prótese", "1800.00"),
)

TEAM = (
    ("beatriz.demo@example.com", "Dra. Beatriz Demo", Role.DENTISTA, "CRO-SP 00001"),
    ("rafael.demo@example.com", "Dr. Rafael Demo", Role.DENTISTA, "CRO-SP 00002"),
    ("recepcao.demo@example.com", "Júlia Recepção Demo", Role.RECEPCAO, None),
    ("gestor.demo@example.com", "Marcos Gestor Demo", Role.GESTOR, None),
)


class DemoError(Exception):
    pass


@dataclass
class Report:
    clinic: str = ""
    created: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def _years_ago(years: int, today: date) -> date:
    return today.replace(year=today.year - years, day=min(today.day, 28))


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=_tz())


# ---------- clínica e equipe (tabelas globais) ----------


def _clinic_and_admin(db: Session, slug: str, report: Report) -> tuple[Clinic, User]:
    clinic = db.scalar(select(Clinic).where(Clinic.slug == slug))
    if clinic is None:
        clinic, admin = create_clinic_with_admin(
            db,
            clinic_name="Clínica Demo",
            clinic_slug=slug,
            admin_email=f"admin.{slug}@example.com",
            admin_name="Admin Demo",
            admin_password=DEMO_PASSWORD,
        )
        report.created.append(f"clínica {clinic.name} e admin {admin.email}")
        return clinic, admin
    admin = db.scalar(
        select(User)
        .join(ClinicMembership, ClinicMembership.user_id == User.id)
        .where(
            ClinicMembership.clinic_id == clinic.id,
            ClinicMembership.role == Role.ADMIN,
            ClinicMembership.active,
            User.active,
        )
        .order_by(ClinicMembership.created_at)
        .limit(1)
    )
    if admin is None:
        raise DemoError(f"A clínica '{slug}' não tem admin ativo.")
    report.kept.append(f"clínica {clinic.name} (admin {admin.email})")
    return clinic, admin


def _team(db: Session, clinic: Clinic, report: Report) -> dict[str, User]:
    users: dict[str, User] = {}
    for email, name, role, cro in TEAM:
        email = normalize_email(email)
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email, full_name=name, cro=cro, password_hash=hash_password(DEMO_PASSWORD)
            )
            db.add(user)
            db.flush()
            report.created.append(f"usuário {email} ({role.value})")
        membership = db.scalar(
            select(ClinicMembership).where(
                ClinicMembership.user_id == user.id, ClinicMembership.clinic_id == clinic.id
            )
        )
        if membership is None:
            db.add(ClinicMembership(user_id=user.id, clinic_id=clinic.id, role=role))
            db.flush()
        users[email] = user
    return users


# ---------- dados da clínica (sessão com RLS) ----------


def _chair(db: Session, actor: CurrentUser, report: Report) -> Chair:
    chair = db.scalar(select(Chair).where(Chair.name == DEMO_CHAIR))
    if chair is None:
        chair = agenda.create_chair(db, actor, DEMO_CHAIR)
        report.created.append(f"cadeira {DEMO_CHAIR}")
    return chair


def _price_table(db: Session, actor: CurrentUser, report: Report) -> None:
    table = db.scalar(select(PriceTable).where(PriceTable.name == DEMO_TABLE))
    if table is None:
        table, draft = pricing.create_table(
            db,
            actor,
            name=DEMO_TABLE,
            description="Criada pelo comando de demonstração.",
            parent_table_id=None,
            adjustment_pct=None,
        )
        pricing.replace_items(
            db,
            actor,
            draft,
            [
                {"procedure_code": c, "description": d, "category": cat, "price": Decimal(p)}
                for c, d, cat, p in PROCEDURES
            ],
        )
        pricing.publish(db, actor, table, draft, None)
        report.created.append(f"{DEMO_TABLE} publicada com {len(PROCEDURES)} procedimentos")
    has_assignment = db.scalar(
        select(PriceAssignment.id).where(
            PriceAssignment.table_id == table.id, PriceAssignment.scope_type == ScopeType.CLINICA
        )
    )
    if has_assignment is None:
        pricing.create_assignment(
            db, actor, table_id=table.id, scope_type=ScopeType.CLINICA, scope_id=None, priority=None
        )


def _legend(db: Session, clinic_id: uuid.UUID) -> dict[str, uuid.UUID]:
    odontograma.ensure_default_legend(db, clinic_id)
    return {s.code: s.id for s in db.scalars(select(ToothStatus))}


def _marks(
    db: Session,
    actor: CurrentUser,
    patient: Patient,
    legend: dict[str, uuid.UUID],
    marks: list[tuple[int, str | None, str]],
) -> None:
    current = odontograma.current_marks(db, patient)
    events = [
        {"tooth": tooth, "face": face, "status_id": legend[code], "action": "marcar"}
        for tooth, face, code in marks
        if code in legend and (tooth, face, legend[code]) not in current
    ]
    if events:
        odontograma.record_events(db, actor, patient, None, events)


@dataclass(frozen=True)
class DemoPatient:
    data: dict
    arch: dict
    marks: list[tuple[int, str | None, str]]
    consent_by: ConsentGivenBy


def _patients(today: date) -> list[DemoPatient]:
    return [
        DemoPatient(
            data={
                "full_name": "Carlos Demo Andrade",
                "phone": "11987650001",
                "birth_date": _years_ago(41, today),
                "sex": Sex.MASCULINO,
                "email": "carlos.demo@example.com",
                "city": "São Paulo",
                "state": "SP",
                "notes": "Paciente de demonstração (adulto).",
            },
            arch={"dentition": "permanente", "third_molars": [38, 48]},
            marks=[
                (16, "O", "carie"),
                (25, "D", "carie"),
                (16, "O", "restauracao_planejada"),
                (25, "D", "restauracao_planejada"),
                (26, "O", "restauracao"),
                (26, "M", "restauracao"),
                (36, None, "endodontia"),
                (36, None, "coroa"),
                (46, None, "ausente"),
                (47, None, "endodontia_planejada"),
            ],
            consent_by=ConsentGivenBy.PACIENTE,
        ),
        DemoPatient(
            data={
                "full_name": "Laura Demo Costa",
                "phone": "11987650002",
                "birth_date": _years_ago(4, today),
                "sex": Sex.FEMININO,
                "guardian_name": "Mariana Demo Costa",
                "guardian_phone": "11987650003",
                "guardian_relationship": "mãe",
                "notes": "Paciente de demonstração (criança, dentição decídua).",
            },
            arch={"dentition": "decidua"},
            marks=[
                (54, "O", "carie"),
                (64, "O", "carie"),
                (55, "O", "selante"),
                (65, "O", "selante"),
            ],
            consent_by=ConsentGivenBy.RESPONSAVEL,
        ),
        DemoPatient(
            data={
                "full_name": "Pedro Demo Souza",
                "phone": "11987650004",
                "birth_date": _years_ago(9, today),
                "sex": Sex.MASCULINO,
                "guardian_name": "Ricardo Demo Souza",
                "guardian_phone": "11987650005",
                "guardian_relationship": "pai",
                "notes": "Paciente de demonstração (dentição mista).",
            },
            arch={"dentition": "mista"},
            marks=[
                (75, "O", "carie"),
                (85, None, "extracao_indicada"),
                (36, "O", "selante"),
                (46, "O", "selante"),
            ],
            consent_by=ConsentGivenBy.RESPONSAVEL,
        ),
    ]


def _patient(
    db: Session,
    actor: CurrentUser,
    demo: DemoPatient,
    legend: dict[str, uuid.UUID],
    report: Report,
) -> tuple[Patient, bool]:
    patient = db.scalar(select(Patient).where(Patient.full_name == demo.data["full_name"]))
    if patient is not None:
        report.kept.append(f"paciente {patient.full_name}")
        return patient, False
    patient = pacientes.create_patient(db, actor, dict(demo.data))
    pacientes.record_consent(
        db,
        actor,
        patient,
        {
            "purpose": ConsentPurpose.TRATAMENTO_DADOS,
            "granted": True,
            "given_by": demo.consent_by,
            "term_version": "demo",
        },
    )
    odontograma.record_arch(db, actor, patient, dict(demo.arch))
    _marks(db, actor, patient, legend, demo.marks)
    report.created.append(f"paciente {patient.full_name} ({demo.arch['dentition']})")
    return patient, True


def _plan_for_adult(
    db: Session,
    actor: CurrentUser,
    patient: Patient,
    dentist_id: uuid.UUID,
    legend: dict[str, uuid.UUID],
    report: Report,
) -> None:
    if db.scalar(select(TreatmentPlan.id).where(TreatmentPlan.patient_id == patient.id)):
        return
    plan = tratamento.create_plan(
        db,
        actor,
        {
            "patient_id": patient.id,
            "dentist_id": dentist_id,
            "title": "Plano inicial",
            "items": [
                {
                    "procedure_code": "DEMO-REST",
                    "tooth": 16,
                    "faces": "O",
                    "planned_status_id": legend["restauracao_planejada"],
                    "done_status_id": legend["restauracao"],
                },
                {
                    "procedure_code": "DEMO-REST",
                    "tooth": 25,
                    "faces": "D",
                    "planned_status_id": legend["restauracao_planejada"],
                    "done_status_id": legend["restauracao"],
                },
                {
                    "procedure_code": "DEMO-ENDO",
                    "tooth": 47,
                    "planned_status_id": legend["endodontia_planejada"],
                    "done_status_id": legend["endodontia"],
                },
                {"procedure_code": "DEMO-PROF"},
            ],
        },
    )
    tratamento.issue(db, actor, plan)
    items = tratamento.plan_items(db, plan)
    tratamento.decide(db, actor, plan, [i.id for i in items])
    report.created.append(f"plano de tratamento aprovado de {patient.full_name}")

    # Um segundo orçamento, emitido e aguardando a resposta do paciente.
    second = tratamento.create_plan(
        db,
        actor,
        {
            "patient_id": patient.id,
            "dentist_id": dentist_id,
            "title": "Reabilitação do 46",
            "items": [{"procedure_code": "DEMO-COROA", "tooth": 46}],
        },
    )
    tratamento.issue(db, actor, second)
    report.created.append(f"orçamento aguardando resposta de {patient.full_name}")


def _appointments(
    db: Session,
    actor: CurrentUser,
    chair: Chair,
    slots: list[tuple[Patient, uuid.UUID, datetime, int, str]],
    report: Report,
) -> None:
    for patient, dentist_id, starts_at, minutes, procedure in slots:
        exists = db.scalar(
            select(Appointment.id).where(
                Appointment.patient_id == patient.id, Appointment.starts_at >= agenda.now()
            )
        )
        if exists is not None:
            continue
        try:
            agenda.create_appointment(
                db,
                actor,
                {
                    "patient_id": patient.id,
                    "dentist_id": dentist_id,
                    "chair_id": chair.id,
                    "starts_at": starts_at,
                    "ends_at": starts_at + timedelta(minutes=minutes),
                    "procedure": procedure,
                },
            )
        except agenda.RuleViolation as exc:  # horário ocupado por dado real: só avisa
            report.kept.append(f"agendamento de {patient.full_name} não criado: {exc.message}")
            continue
        report.created.append(
            f"agendamento de {patient.full_name} em {starts_at:%d/%m %H:%M} ({procedure})"
        )


def seed(slug: str) -> Report:
    if get_settings().environment == "production":
        raise DemoError("Dados de demonstração não são criados em produção.")
    report = Report()
    with get_sessionmaker()() as db:
        clinic, admin = _clinic_and_admin(db, slug, report)
        team = _team(db, clinic, report)
        db.commit()
    report.clinic = clinic.name

    actor = CurrentUser(user_id=admin.id, clinic_id=clinic.id, role=Role.ADMIN)
    dentist = team["beatriz.demo@example.com"]
    other = team["rafael.demo@example.com"]
    today = pacientes.today()
    with tenant_session(clinic.id) as db:
        chair = _chair(db, actor, report)
        _price_table(db, actor, report)
        legend = _legend(db, clinic.id)
        created = {}
        for demo in _patients(today):
            patient, _ = _patient(db, actor, demo, legend, report)
            created[demo.data["full_name"]] = patient
        adult = created["Carlos Demo Andrade"]
        _plan_for_adult(db, actor, adult, dentist.id, legend, report)
        tomorrow = today + timedelta(days=1)
        _appointments(
            db,
            actor,
            chair,
            [
                (created["Laura Demo Costa"], dentist.id, _at(tomorrow, 9), 30, "Avaliação"),
                (created["Pedro Demo Souza"], other.id, _at(tomorrow, 10), 45, "Selantes"),
                (adult, dentist.id, _at(today + timedelta(days=2), 14), 60, "Restauração 16"),
            ],
            report,
        )
        audit.record(
            db,
            actor,
            "demo.dados_criados",
            details={"criados": len(report.created)},
        )
        db.commit()
    return report
