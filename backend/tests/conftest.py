"""Configuração dos testes.

Testes unitários rodam sem banco. Testes marcados com `integration` precisam de
um PostgreSQL com o role `odonto_app` criado (docker/postgres/roles.sql) e das
variáveis TEST_DATABASE_URL e TEST_MIGRATIONS_DATABASE_URL. Sem elas, são pulados.
"""

import os
from pathlib import Path

import pytest

TEST_DB = os.getenv("TEST_DATABASE_URL")
TEST_MIGRATIONS_DB = os.getenv("TEST_MIGRATIONS_DATABASE_URL")
HAS_DB = bool(TEST_DB and TEST_MIGRATIONS_DB)

# Precisa acontecer antes de qualquer import de `app` (as configurações são cacheadas).
if HAS_DB:
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ["MIGRATIONS_DATABASE_URL"] = TEST_MIGRATIONS_DB
os.environ["JWT_SECRET"] = "segredo-de-teste-com-tamanho-suficiente"

BACKEND_DIR = Path(__file__).resolve().parent.parent


def pytest_collection_modifyitems(config, items):
    if HAS_DB:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL/TEST_MIGRATIONS_DATABASE_URL não definidos")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db():
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture
def owner_engine(migrated_db):
    from sqlalchemy import create_engine

    engine = create_engine(TEST_MIGRATIONS_DB)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(owner_engine):
    """Limpa os dados antes de cada teste (TRUNCATE não passa pelo RLS)."""
    from sqlalchemy import text

    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE odontogram_events, tooth_statuses, "
                "clinical_note_signatures, encounter_transfers, clinical_notes, encounters, "
                "anamnesis_responses, anamnesis_template_versions, anamnesis_templates, "
                "appointment_events, appointments, chairs, patient_consents, patients, "
                "cost_sheet_items, cost_sheets, pricing_variables, materials, "
                "import_jobs, import_profiles, price_snapshots, price_assignments, "
                "price_items, price_table_versions, "
                "price_tables, audit_logs, clinic_memberships, users, clinics "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture
def db_session(clean_db):
    from app.core.db import get_sessionmaker

    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client(clean_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_clinic(db_session):
    """Cria clínica + usuário vinculado. Retorna (clinic, user, password)."""
    from app.core.roles import Role
    from app.core.security import hash_password
    from app.modules.identidade.models import Clinic, ClinicMembership, User

    password = "senha-forte-123"
    counter = {"n": 0}

    def _make(role: Role = Role.ADMIN, email: str | None = None, user=None):
        counter["n"] += 1
        n = counter["n"]
        clinic = Clinic(name=f"Clínica {n}", slug=f"clinica-{n}")
        db_session.add(clinic)
        if user is None:
            user = User(
                email=email or f"user{n}@exemplo.com",
                full_name=f"Usuário {n}",
                password_hash=hash_password(password),
            )
            db_session.add(user)
        db_session.flush()
        db_session.add(ClinicMembership(user_id=user.id, clinic_id=clinic.id, role=role))
        db_session.commit()
        return clinic, user, password

    return _make


@pytest.fixture
def add_member(db_session):
    """Cria um usuário e vincula a uma clínica existente. Retorna (user, password)."""
    from app.core.security import hash_password
    from app.modules.identidade.models import ClinicMembership, User

    password = "senha-forte-123"
    counter = {"n": 0}

    def _add(clinic, role):
        counter["n"] += 1
        user = User(
            email=f"membro{counter['n']}-{clinic.slug}@exemplo.com",
            full_name=f"Membro {counter['n']}",
            password_hash=hash_password(password),
        )
        db_session.add(user)
        db_session.flush()
        db_session.add(ClinicMembership(user_id=user.id, clinic_id=clinic.id, role=role))
        db_session.commit()
        return user, password

    return _add
