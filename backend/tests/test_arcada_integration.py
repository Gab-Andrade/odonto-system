"""Arcada do paciente: sugestão pela idade, registro, arcada em qualquer data, papéis,
garantias no banco e isolamento entre clínicas."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_odontograma_integration import _setup

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.modules.odontograma.models import ArchConfig

pytestmark = pytest.mark.integration


def _url(ctx, patient=None):
    return f"/odontograma/pacientes/{patient or ctx['patient']}/arcada"


def _post(client, ctx, body, who="dent", expect=201, patient=None):
    resp = client.post(_url(ctx, patient), json=body, headers=ctx["h"][who])
    assert resp.status_code == expect, resp.text
    return resp.json()


def test_default_then_recorded(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    resp = client.get(_url(ctx), headers=ctx["h"]["asb"])
    assert resp.status_code == 200, resp.text
    default = resp.json()
    assert default["source"] == "padrao" and default["dentition"] == "permanente"
    assert len(default["teeth"]) == 32 and default["third_molars"] == [18, 28, 48, 38]
    assert default["id"] is None

    adult = client.post(
        "/pacientes",
        json={"full_name": "Carlos", "phone": "11911113333", "birth_date": "1980-05-01"},
        headers=ctx["h"]["recep"],
    ).json()
    assert len(client.get(_url(ctx, adult["id"]), headers=ctx["h"]["dent"]).json()["teeth"]) == 32

    before = datetime.now(UTC)
    rec = _post(client, ctx, {"dentition": "permanente", "third_molars": [38, 48]})
    assert rec["source"] == "registrada" and len(rec["teeth"]) == 30
    assert rec["third_molars"] == [48, 38] and rec["id"]

    mixed = _post(
        client,
        ctx,
        {"dentition": "mista", "teeth": [16, 55, 11, 21, 65, 26, 36, 75, 46, 85], "notes": "x"},
        who="asb",
    )
    assert mixed["teeth"] == [16, 55, 11, 21, 65, 26, 46, 85, 75, 36]

    now = client.get(_url(ctx), headers=ctx["h"]["gestor"]).json()
    assert now["id"] == mixed["id"] and now["notes"] == "x"
    then = client.get(_url(ctx), params={"em": before.isoformat()}, headers=ctx["h"]["dent"])
    assert then.json()["source"] == "padrao"

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"odontograma.arcada_lida", "odontograma.arcada_registrada"} <= actions


def test_rules_and_roles(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _post(client, ctx, {"dentition": "decidua", "third_molars": [18]}, expect=409)
    _post(client, ctx, {"dentition": "mista", "teeth": [11, 51]}, expect=409)  # mesma vaga
    _post(client, ctx, {"dentition": "permanente", "teeth": [11, 51]}, expect=409)
    _post(client, ctx, {"dentition": "permanente", "teeth": [11], "third_molars": [18]},
          expect=409)  # fmt: skip
    _post(client, ctx, {"dentition": "permanente", "teeth": [19]}, expect=422)
    _post(client, ctx, {"dentition": "adulta"}, expect=422)
    assert len(_post(client, ctx, {"dentition": "decidua"})["teeth"]) == 20

    _post(client, ctx, {"dentition": "decidua"}, who="gestor", expect=403)
    _post(client, ctx, {"dentition": "decidua"}, who="recep", expect=403)
    _post(client, ctx, {"dentition": "decidua"}, who="admin")
    assert client.get(_url(ctx), headers=ctx["h"]["recep"]).status_code == 403
    _post(client, ctx, {"dentition": "decidua"}, patient=str(uuid.uuid4()), expect=404)

    resp = client.patch(
        f"/pacientes/{ctx['patient']}", json={"active": False}, headers=ctx["h"]["admin"]
    )
    assert resp.status_code == 200 and resp.json()["active"] is False, resp.text
    _post(client, ctx, {"dentition": "decidua"}, expect=409)


def test_database_guards_and_isolation(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    _post(client, a, {"dentition": "permanente"})

    assert client.get(_url(a), headers=b["h"]["admin"]).status_code == 404
    _post(client, b, {"dentition": "decidua"}, who="admin", patient=a["patient"], expect=404)

    cid = a["clinic"].id
    for sql in ("UPDATE dental_arch_configs SET notes = 'x'", "DELETE FROM dental_arch_configs"):
        with tenant_session(cid) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))

    for teeth in ([19], []):
        with tenant_session(cid) as s:
            s.add(
                ArchConfig(
                    clinic_id=cid,
                    patient_id=uuid.UUID(a["patient"]),
                    dentition="permanente",
                    teeth=teeth,
                )
            )
            with pytest.raises(IntegrityError, match="teeth_fdi"):
                s.flush()

    with tenant_session(b["clinic"].id) as s:
        assert s.scalar(select(func.count()).select_from(ArchConfig)) == 0
        # FK composta: B não grava arcada no paciente de A.
        s.add(
            ArchConfig(
                clinic_id=b["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                dentition="permanente",
                teeth=[11],
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
