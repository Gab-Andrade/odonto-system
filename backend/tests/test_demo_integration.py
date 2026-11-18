"""Comando de dados de demonstração (`python -m app.cli demo`)."""

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def _counts(clinic_id):
    from app.core.db import tenant_session
    from app.modules.agenda.models import Appointment
    from app.modules.odontograma.models import ArchConfig, OdontogramEvent, ToothNote
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
                ToothNote,
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
    assert counts["Patient"] == 4
    assert counts["ArchConfig"] == 4
    assert counts["TreatmentPlan"] == 3
    assert counts["Appointment"] == 4
    assert counts["OdontogramEvent"] > 10
    assert counts["Encounter"] == 3
    assert counts["AnamnesisResponse"] == 2
    assert counts["ToothNote"] == 1

    second = demo.seed("demo-teste")
    assert second.created == []
    assert _counts(clinic.id) == counts


def test_demo_uses_existing_clinic(make_clinic):
    from app import demo

    clinic, user, _ = make_clinic()
    report = demo.seed(clinic.slug)
    assert any(user.email in line for line in report.kept)
    assert _counts(clinic.id)["Patient"] == 4


def test_demo_refused_in_production(monkeypatch):
    from app import demo

    class _Prod:
        environment = "production"

    monkeypatch.setattr(demo, "get_settings", lambda: _Prod())
    with pytest.raises(demo.DemoError):
        demo.seed("qualquer")


def test_demo_adds_missing_procedures_to_old_table(clean_db, monkeypatch):
    """Clínica criada por um demo antigo (sem o retratamento): o demo novo publica uma
    versão da tabela com o que falta, e o plano do Cadu sai com preço."""
    from app import demo
    from app.core.db import get_sessionmaker, tenant_session
    from app.modules.identidade.models import Clinic
    from app.modules.precificacao import service as pricing
    from app.modules.precificacao.models import PriceTable

    full = demo.PROCEDURES
    monkeypatch.setattr(demo, "PROCEDURES", tuple(p for p in full if p[0] != "DEMO-RETRAT"))
    monkeypatch.setattr(demo, "_cadu_plan", lambda *a, **k: None)
    demo.seed("demo-antiga")

    monkeypatch.undo()
    report = demo.seed("demo-antiga")
    assert any("DEMO-RETRAT" in line for line in report.created)
    with get_sessionmaker()() as s:
        clinic = s.scalar(select(Clinic).where(Clinic.slug == "demo-antiga"))
    with tenant_session(clinic.id) as s:
        table = s.scalar(select(PriceTable).where(PriceTable.name == demo.DEMO_TABLE))
        version = pricing.effective_version(s, table.id, pricing.today())
        codes = {i.procedure_code for i in pricing.list_items(s, version)}
    assert codes == {p[0] for p in full}
    assert _counts(clinic.id)["TreatmentPlan"] == 3
