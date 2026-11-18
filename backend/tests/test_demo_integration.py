"""Comando de dados de demonstração (`python -m app.cli demo`)."""

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def _counts(clinic_id):
    from app.core.db import tenant_session
    from app.modules.agenda.models import Appointment
    from app.modules.odontograma.models import ArchConfig, OdontogramEvent
    from app.modules.pacientes.models import Patient
    from app.modules.prontuario.models import AnamnesisResponse, Encounter
    from app.modules.tratamento.models import TreatmentPlan

    with tenant_session(clinic_id) as s:
        return {
            m.__name__: s.scalar(select(func.count()).select_from(m))
            for m in (
                Patient,
                ArchConfig,
                OdontogramEvent,
                TreatmentPlan,
                Appointment,
                Encounter,
                AnamnesisResponse,
            )
        }


def test_demo_creates_clinic_and_is_idempotent(clean_db):
    from app import demo
    from app.core.db import get_sessionmaker
    from app.modules.identidade.models import Clinic

    first = demo.seed("demo-teste")
    assert first.created
    with get_sessionmaker()() as s:
        clinic = s.scalar(select(Clinic).where(Clinic.slug == "demo-teste"))
    counts = _counts(clinic.id)
    assert counts["Patient"] == 3
    assert counts["ArchConfig"] == 3
    assert counts["TreatmentPlan"] == 2
    assert counts["Appointment"] == 3
    assert counts["OdontogramEvent"] > 10
    assert counts["Encounter"] == 2
    assert counts["AnamnesisResponse"] == 1

    second = demo.seed("demo-teste")
    assert second.created == []
    assert _counts(clinic.id) == counts


def test_demo_uses_existing_clinic(make_clinic):
    from app import demo

    clinic, user, _ = make_clinic()
    report = demo.seed(clinic.slug)
    assert any(user.email in line for line in report.kept)
    assert _counts(clinic.id)["Patient"] == 3


def test_demo_refused_in_production(monkeypatch):
    from app import demo

    class _Prod:
        environment = "production"

    monkeypatch.setattr(demo, "get_settings", lambda: _Prod())
    with pytest.raises(demo.DemoError):
        demo.seed("qualquer")
