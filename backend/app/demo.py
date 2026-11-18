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
from app.modules.estoque import lotes_service as estoque_lotes
from app.modules.estoque import service as estoque
from app.modules.estoque.models import Material
from app.modules.financeiro import service as financeiro
from app.modules.financeiro.models import Payable, PaymentMethod, Receivable
from app.modules.identidade.models import Clinic, ClinicMembership, User
from app.modules.identidade.service import create_clinic_with_admin, normalize_email
from app.modules.odontograma import service as odontograma
from app.modules.odontograma.models import StatusKind, StatusRegion, StatusScope, ToothStatus
from app.modules.pacientes import service as pacientes
from app.modules.pacientes.models import ConsentGivenBy, ConsentPurpose, Patient, Sex
from app.modules.precificacao import service as pricing
from app.modules.precificacao.models import PriceAssignment, PriceTable, ScopeType
from app.modules.prontuario import atendimento_service as atendimento
from app.modules.prontuario import service as prontuario
from app.modules.prontuario.models import (
    AnamnesisTemplate,
    Encounter,
    EncounterStatus,
    VersionStatus,
)
from app.modules.repasse import service as repasse
from app.modules.repasse.models import CommissionRule
from app.modules.tratamento import service as tratamento
from app.modules.tratamento.models import ItemStatus, TreatmentPlan, TreatmentPlanItem

DEMO_PASSWORD = "demo-odonto-2026"  # noqa: S105 - só para dados locais de demonstração
DEMO_TABLE = "Tabela Demo"
DEMO_CHAIR = "Cadeira Demo"
DEMO_ANAMNESE = "Anamnese geral (demo)"

# Procedimentos da tabela de demonstração (código, descrição, categoria, preço).
PROCEDURES = (
    ("DEMO-PROF", "Profilaxia (limpeza)", "Prevenção", "180.00"),
    ("DEMO-REST", "Restauração em resina", "Dentística", "250.00"),
    ("DEMO-ENDO", "Tratamento de canal (molar)", "Endodontia", "1200.00"),
    ("DEMO-EXO", "Extração simples", "Cirurgia", "220.00"),
    ("DEMO-SEL", "Selante (por dente)", "Prevenção", "90.00"),
    ("DEMO-COROA", "Coroa em porcelana", "Prótese", "1800.00"),
    ("DEMO-RETRAT", "Retratamento endodôntico (molar)", "Endodontia", "1500.00"),
)

ANAMNESE = [
    {
        "id": "alergia",
        "text": "Tem alergia a algum medicamento ou material?",
        "type": "sim_nao",
        "section": "Saúde geral",
        "required": True,
        "alert": True,
    },
    {"id": "alergia_quais", "text": "Se sim, quais?", "type": "texto", "section": "Saúde geral"},
    {
        "id": "medicamentos",
        "text": "Usa algum medicamento?",
        "type": "texto",
        "section": "Saúde geral",
    },
    {
        "id": "anticoagulante",
        "text": "Usa anticoagulante?",
        "type": "sim_nao",
        "section": "Saúde geral",
        "alert": True,
    },
    {
        "id": "diabetes",
        "text": "Tem diabetes?",
        "type": "sim_nao",
        "section": "Saúde geral",
        "alert": True,
    },
    {
        "id": "pressao",
        "text": "Pressão arterial",
        "type": "escolha_unica",
        "section": "Saúde geral",
        "options": ["Normal", "Alta", "Baixa", "Não sabe"],
        "alert": True,
        "alert_options": ["Alta"],
    },
    {
        "id": "fumante",
        "text": "Fuma?",
        "type": "escolha_unica",
        "section": "Hábitos",
        "options": ["Não", "Sim", "Ex-fumante"],
    },
    {"id": "escovacoes", "text": "Escovações por dia", "type": "numero", "section": "Hábitos"},
    {
        "id": "queixa",
        "text": "Queixa principal",
        "type": "texto",
        "section": "Motivo da consulta",
        "required": True,
    },
]

TEAM = (
    ("beatriz.demo@example.com", "Dra. Beatriz Demo", Role.DENTISTA, "CRO-SP 00001"),
    ("rafael.demo@example.com", "Dr. Rafael Demo", Role.DENTISTA, "CRO-SP 00002"),
    ("giovanna.demo@example.com", "Dra. Giovanna Andrade", Role.DENTISTA, "CRO-SP 00003"),
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
        elif user.full_name != name:  # usuário de demonstração: o nome segue o do código
            report.created.append(f"nome de {email}: {user.full_name} → {name}")
            user.full_name = name
            db.flush()
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
    else:
        _add_missing_procedures(db, actor, table, report)
    has_assignment = db.scalar(
        select(PriceAssignment.id).where(
            PriceAssignment.table_id == table.id, PriceAssignment.scope_type == ScopeType.CLINICA
        )
    )
    if has_assignment is None:
        pricing.create_assignment(
            db, actor, table_id=table.id, scope_type=ScopeType.CLINICA, scope_id=None, priority=None
        )


def _add_missing_procedures(
    db: Session, actor: CurrentUser, table: PriceTable, report: Report
) -> None:
    """Tabela criada por uma versão anterior do demo: publica uma versão nova com os
    procedimentos que faltam (ex.: o retratamento), mantendo os preços que já estão lá."""
    current = pricing.effective_version(db, table.id, pricing.today())
    have = {i.procedure_code for i in pricing.list_items(db, current)} if current else set()
    missing = [p for p in PROCEDURES if p[0] not in have]
    if not missing:
        return
    draft = pricing.create_draft(db, actor, table)
    items = [
        {
            "procedure_code": i.procedure_code,
            "description": i.description,
            "category": i.category,
            "price": i.price,
        }
        for i in pricing.list_items(db, draft)
    ]
    items += [
        {"procedure_code": c, "description": d, "category": cat, "price": Decimal(p)}
        for c, d, cat, p in missing
    ]
    pricing.replace_items(db, actor, draft, items)
    pricing.publish(db, actor, table, draft, None)
    report.created.append(f"{DEMO_TABLE}: nova versão com {', '.join(m[0] for m in missing)}")


def _anamnese(db: Session, actor: CurrentUser, report: Report) -> AnamnesisTemplate:
    template = db.scalar(select(AnamnesisTemplate).where(AnamnesisTemplate.name == DEMO_ANAMNESE))
    if template is None:
        template, draft = prontuario.create_template(
            db, actor, DEMO_ANAMNESE, "Criado pelo comando de demonstração.", ANAMNESE
        )
        prontuario.publish(db, actor, draft)
        report.created.append(f"modelo de anamnese publicado: {DEMO_ANAMNESE}")
    return template


def _clinical_history(
    db: Session,
    dentist: CurrentUser,
    template: AnamnesisTemplate,
    patient: Patient,
    report: Report,
) -> None:
    """Anamnese respondida (com alerta de alergia) e atendimentos do adulto: um fechado
    com evolução e um aberto há 3 dias (aparece no alerta "atendimento aberto")."""
    if db.scalar(select(Encounter.id).where(Encounter.patient_id == patient.id)) is not None:
        return
    version = prontuario.open_versions(db, [template.id])[template.id][VersionStatus.PUBLICADA]
    prontuario.record_response(
        db,
        dentist,
        patient,
        template.id,
        version.id,
        {
            "alergia": True,
            "alergia_quais": "Dipirona",
            "medicamentos": "Losartana 50 mg",
            "anticoagulante": False,
            "diabetes": False,
            "pressao": "Alta",
            "fumante": "Ex-fumante",
            "escovacoes": 2,
            "queixa": "Sensibilidade no dente 16 ao tomar gelado.",
        },
    )
    first = atendimento.open_encounter(
        db, dentist, patient.id, None, atendimento.now() - timedelta(days=6)
    )
    atendimento.add_note(
        db,
        dentist,
        first,
        "Avaliação inicial. Cárie oclusal no 16 e distal no 25; 47 com indicação de "
        "tratamento de canal. Orientada higiene e solicitado raio-X panorâmico.",
        None,
    )
    atendimento.close_encounter(db, dentist, first)
    atendimento.open_encounter(db, dentist, patient.id, None, atendimento.now() - timedelta(days=3))
    report.created.append(f"anamnese e atendimentos de {patient.full_name}")


# Itens que a clínica de demonstração acrescenta à legenda padrão (mostra que ela é editável).
EXTRA_LEGEND = (
    ("lesao_periapical", "Lesão periapical", "#6A1B9A", "patologia", "dente", 25, "raiz"),
    (
        "retratamento_planejado",
        "Retratamento de canal a fazer",
        "#FF8F00",
        "planejado",
        "dente",
        45,
        "raiz",
    ),
    ("retratamento", "Retratamento de canal", "#00838F", "realizado", "dente", 85, "raiz"),
)


def _legend(db: Session, actor: CurrentUser, report: Report) -> dict[str, uuid.UUID]:
    odontograma.ensure_default_legend(db, actor.clinic_id)
    codes = set(db.scalars(select(ToothStatus.code)))
    for code, name, color, kind, scope, order, region in EXTRA_LEGEND:
        if code not in codes:
            odontograma.create_status(
                db,
                actor,
                {
                    "code": code,
                    "name": name,
                    "color": color,
                    "kind": StatusKind(kind),
                    "scope": StatusScope(scope),
                    "sort_order": order,
                    "region": StatusRegion(region),
                },
            )
            report.created.append(f"item da legenda {name}")
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


# Caso para apresentação: retratamento endodôntico do 36, com a Dra. Giovanna.
CADU = DemoPatient(
    data={
        "full_name": "Cadu Lima",
        "phone": "11987650006",
        "birth_date": None,  # preenchido em seed() a partir de hoje
        "sex": Sex.MASCULINO,
        "email": "cadu.demo@example.com",
        "city": "São Paulo",
        "state": "SP",
        "notes": "Paciente de demonstração: retratamento de canal do 36.",
    },
    arch={"dentition": "permanente", "third_molars": []},
    marks=[
        (36, None, "endodontia"),  # canal feito há anos, em outro consultório
        (36, None, "coroa"),
        (36, None, "lesao_periapical"),
        (36, None, "retratamento_planejado"),
        (26, "O", "restauracao"),
        (17, "O", "restauracao"),
        (45, "D", "carie"),
        (45, "D", "restauracao_planejada"),
    ],
    consent_by=ConsentGivenBy.PACIENTE,
)


def _cadu_history(
    db: Session,
    dentist: CurrentUser,
    template: AnamnesisTemplate,
    patient: Patient,
    report: Report,
) -> None:
    """Anamnese, primeira consulta com a evolução que indica o retratamento e anotação no 36."""
    if db.scalar(select(Encounter.id).where(Encounter.patient_id == patient.id)) is not None:
        return
    version = prontuario.open_versions(db, [template.id])[template.id][VersionStatus.PUBLICADA]
    prontuario.record_response(
        db,
        dentist,
        patient,
        template.id,
        version.id,
        {
            "alergia": False,
            "medicamentos": "Nenhum",
            "anticoagulante": False,
            "diabetes": False,
            "pressao": "Normal",
            "fumante": "Não",
            "escovacoes": 3,
            "queixa": "Dor ao mastigar do lado esquerdo, embaixo, há cerca de um mês.",
        },
    )
    first = atendimento.open_encounter(
        db, dentist, patient.id, None, atendimento.now() - timedelta(days=5)
    )
    atendimento.add_note(
        db,
        dentist,
        first,
        "Paciente relata dor à mastigação no 36, tratado endodonticamente há cerca de 6 anos "
        "em outro consultório e com coroa. Percussão vertical positiva, palpação apical "
        "levemente dolorosa, sem fístula. Radiografia periapical: obturação aquém do ápice "
        "(cerca de 3 mm) e área radiolúcida periapical na raiz mesial. Diagnóstico: "
        "periodontite apical sintomática em dente com tratamento endodôntico prévio. "
        "Indicado retratamento endodôntico do 36 e, depois, nova coroa. Cárie distal no 45. "
        "Paciente orientado sobre o prognóstico e as sessões; aceitou o plano.",
        None,
    )
    atendimento.close_encounter(db, dentist, first)
    odontograma.add_tooth_note(
        db,
        dentist,
        patient,
        36,
        "Obturação antiga curta (~3 mm aquém) e lesão periapical na raiz mesial. Suspeita de "
        "canal mesiolingual não tratado. Remover a coroa, desobturar e reavaliar com "
        "localizador apical. Medicação intracanal com hidróxido de cálcio entre as sessões.",
    )
    report.created.append(f"anamnese, atendimento e anotação do 36 de {patient.full_name}")


def _cadu_plan(
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
            "title": "Retratamento endodôntico do 36",
            "items": [
                {
                    "procedure_code": "DEMO-RETRAT",
                    "tooth": 36,
                    "planned_status_id": legend["retratamento_planejado"],
                    "done_status_id": legend["retratamento"],
                },
                {"procedure_code": "DEMO-COROA", "tooth": 36},
                {
                    "procedure_code": "DEMO-REST",
                    "tooth": 45,
                    "faces": "D",
                    "planned_status_id": legend["restauracao_planejada"],
                    "done_status_id": legend["restauracao"],
                },
            ],
        },
    )
    tratamento.issue(db, actor, plan)
    tratamento.decide(db, actor, plan, [i.id for i in tratamento.plan_items(db, plan)])
    report.created.append(f"plano aprovado de {patient.full_name} (retratamento do 36)")


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


# ---------- gestão: estoque, contas a pagar e repasse ----------

# (nome, unidade, categoria, custo, mínimo, lotes: (qtd, dias p/ vencer | None, dias da compra))
MATERIALS = (
    ("Resina composta A2", "tubo", "Dentística", "89.90", "3", [("2", 20, 30)]),
    ("Luva de procedimento", "cx", "Descartáveis", "32.50", "5", [("12", 400, 10)]),
    ("Anestésico lidocaína 2%", "un", "Anestesia", "2.80", "50",
     [("120", 200, 15), ("10", -10, 200)]),
    ("Lima endodôntica", "un", "Endodontia", "18.00", "6", [("10", None, 40)]),
)  # fmt: skip


def _stock(db: Session, actor: CurrentUser, today: date, report: Report) -> None:
    """Materiais com lotes: um abaixo do mínimo e vencendo, um com lote vencido."""
    if db.scalar(select(Material.id).limit(1)) is not None:
        return
    for name, unit, category, cost, minimum, lots in MATERIALS:
        material = estoque.create_material(
            db, actor, name=name, unit=unit, category=category,
            unit_cost=Decimal(cost), min_quantity=Decimal(minimum),
        )  # fmt: skip
        for n, (qty, expires, received) in enumerate(lots, start=1):
            estoque_lotes.register_entry(
                db,
                actor,
                {
                    "material_id": material.id,
                    "quantity": Decimal(qty),
                    "unit_cost": Decimal(cost),
                    "lot_code": f"DEMO-{name[:3].upper()}-{n}",
                    "expires_on": today + timedelta(days=expires) if expires is not None else None,
                    "supplier": "Dental Demo Distribuidora",
                    "received_on": today - timedelta(days=received),
                },
                can_set_cost=True,
            )
    report.created.append(f"{len(MATERIALS)} materiais com lotes no estoque")


def _payables(db: Session, actor: CurrentUser, today: date, report: Report) -> None:
    """Contas a pagar: uma paga, uma em atraso e uma a vencer."""
    if db.scalar(select(Payable.id).limit(1)) is not None:
        return
    paid = financeiro.create_payable(
        db, actor, {"supplier": "Dental Demo Distribuidora", "category": "Material",
                    "description": "Reposição de resinas e anestésicos",
                    "due_date": today - timedelta(days=12), "amount": Decimal("820.00")},
    )  # fmt: skip
    financeiro.pay_payable(db, paid, PaymentMethod.PIX, today - timedelta(days=12))
    financeiro.create_payable(
        db, actor, {"supplier": "Laboratório Prótese Demo", "category": "Laboratório",
                    "description": "Coroa provisória", "due_date": today - timedelta(days=5),
                    "amount": Decimal("650.00")},
    )  # fmt: skip
    financeiro.create_payable(
        db, actor, {"supplier": "Imobiliária Demo", "category": "Aluguel", "description": None,
                    "due_date": today + timedelta(days=7), "amount": Decimal("4500.00")},
    )  # fmt: skip
    report.created.append("3 contas a pagar (paga, em atraso e a vencer)")


def _commission(
    db: Session,
    actor: CurrentUser,
    dentist: CurrentUser,
    patient: Patient,
    team: dict[str, User],
    today: date,
    report: Report,
) -> None:
    """Regras de repasse e, no plano do adulto, entrada paga e profilaxia realizada, para a
    prévia do repasse da dentista ter o que mostrar."""
    if db.scalar(select(CommissionRule.id).limit(1)) is not None:
        return
    since = today - timedelta(days=60)
    for email, pct in (
        ("beatriz.demo@example.com", "40"),
        ("rafael.demo@example.com", "35"),
        ("giovanna.demo@example.com", "45"),
    ):
        repasse.create_rule(
            db, actor, {"dentist_id": team[email].id, "procedure_code": None,
                        "kind": "percentual", "value": Decimal(pct), "deduct_materials": True,
                        "deduct_card_fee": True, "valid_from": since},
        )  # fmt: skip
    report.created.append("regras de repasse dos dentistas")

    plan = db.scalar(
        select(TreatmentPlan).where(
            TreatmentPlan.patient_id == patient.id, TreatmentPlan.title == "Plano inicial"
        )
    )
    encounter = db.scalar(
        select(Encounter).where(
            Encounter.patient_id == patient.id,
            Encounter.status == EncounterStatus.ABERTO,
            Encounter.dentist_id == dentist.user_id,
        )
    )
    if plan is None or encounter is None:
        return
    if db.scalar(select(Receivable.id).where(Receivable.plan_id == plan.id)) is None:
        rows = financeiro.installment_plan(
            db, actor, plan.id, Decimal("940.00"), 3, today - timedelta(days=2), None
        )
        down = financeiro.get_receivable(db, rows[0].id, lock=True)
        financeiro.register_payment(
            db, actor, down, down.amount, PaymentMethod.PIX, Decimal("0"),
            today - timedelta(days=2), "Entrada (demo)",
        )  # fmt: skip
    prof = db.scalar(
        select(TreatmentPlanItem).where(
            TreatmentPlanItem.plan_id == plan.id,
            TreatmentPlanItem.procedure_code == "DEMO-PROF",
            TreatmentPlanItem.status == ItemStatus.APROVADO,
        )
    )
    if prof is not None:
        tratamento.perform_item(db, dentist, plan, prof, encounter.id)
    report.created.append(f"entrada paga e profilaxia realizada no plano de {patient.full_name}")


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
        legend = _legend(db, actor, report)
        created = {}
        for demo in _patients(today):
            patient, _ = _patient(db, actor, demo, legend, report)
            created[demo.data["full_name"]] = patient
        adult = created["Carlos Demo Andrade"]
        template = _anamnese(db, actor, report)
        as_dentist = CurrentUser(user_id=dentist.id, clinic_id=clinic.id, role=Role.DENTISTA)
        _clinical_history(db, as_dentist, template, adult, report)
        _plan_for_adult(db, actor, adult, dentist.id, legend, report)

        giovanna = team["giovanna.demo@example.com"]
        as_giovanna = CurrentUser(user_id=giovanna.id, clinic_id=clinic.id, role=Role.DENTISTA)
        cadu_demo = DemoPatient(
            data=CADU.data | {"birth_date": _years_ago(34, today)},
            arch=CADU.arch,
            marks=CADU.marks,
            consent_by=CADU.consent_by,
        )
        cadu, _ = _patient(db, actor, cadu_demo, legend, report)
        _cadu_history(db, as_giovanna, template, cadu, report)
        _cadu_plan(db, actor, cadu, giovanna.id, legend, report)

        _stock(db, actor, today, report)
        _payables(db, actor, today, report)
        _commission(db, actor, as_dentist, adult, team, today, report)

        tomorrow = today + timedelta(days=1)
        _appointments(
            db,
            actor,
            chair,
            [
                (created["Laura Demo Costa"], dentist.id, _at(tomorrow, 9), 30, "Avaliação"),
                (created["Pedro Demo Souza"], other.id, _at(tomorrow, 10), 45, "Selantes"),
                (adult, dentist.id, _at(today + timedelta(days=2), 14), 60, "Restauração 16"),
                (
                    cadu,
                    giovanna.id,
                    _at(today + timedelta(days=2), 9),
                    90,
                    "Retratamento de canal 36 (1ª sessão)",
                ),
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
