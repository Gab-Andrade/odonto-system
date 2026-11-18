"""Raio-X (DICOM) no prontuário: envio, listagem, download, classificação, invalidação,
papéis, auditoria e isolamento entre clínicas."""

import pytest
from dicom_fabrica import make_dicom
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import tenant_session
from app.core.roles import Role

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "backend", lambda: storage.LocalBackend(tmp_path))
    return tmp_path


def _login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def ctx(client, make_clinic):
    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    h = _login(client, admin.email, pw)
    r = client.post(
        "/pacientes", json={"full_name": "Ana Silva", "phone": "11988887777"}, headers=h
    )
    assert r.status_code == 201, r.text
    return {"clinic": clinic, "h": h, "patient": r.json()["id"]}


def _send(client, ctx, data, headers=None, **form):
    return client.post(
        f"/imagens/pacientes/{ctx['patient']}/exames",
        files={"arquivo": ("pano.dcm", data, "application/dicom")},
        data=form,
        headers=headers or ctx["h"],
    )


def test_upload_list_detail_download(client, ctx):
    data = make_dicom(modality="PX", study_date="20261110")
    r = _send(client, ctx, data, dentes="36, 37", observacao="Antes do tratamento")
    assert r.status_code == 201, r.text
    exam = r.json()
    assert exam["kind"] == "panoramica"
    assert exam["exam_date"] == "2026-11-10"
    assert exam["teeth"] == [36, 37]
    assert exam["modality"] == "PX"
    assert exam["dicom_patient_name"] == "SILVA^ANA"
    assert exam["size_bytes"] == len(data)
    assert exam["dicom_metadata"]["Manufacturer"] == "Fabricante Teste"

    listed = client.get(f"/imagens/pacientes/{ctx['patient']}/exames", headers=ctx["h"]).json()
    assert [e["id"] for e in listed] == [exam["id"]]
    detail = client.get(f"/imagens/exames/{exam['id']}", headers=ctx["h"])
    assert detail.status_code == 200
    file = client.get(f"/imagens/exames/{exam['id']}/arquivo", headers=ctx["h"])
    assert file.status_code == 200
    assert file.headers["content-type"] == "application/dicom"
    assert file.content == data

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(text("select action from audit_logs")).all())
    assert {
        "imagens.exame_anexado",
        "imagens.exames_listados",
        "imagens.exame_lido",
        "imagens.exame_baixado",
    } <= actions


def test_rejections(client, ctx):
    assert _send(client, ctx, b"nao e dicom" * 20).status_code == 422
    data = make_dicom()
    assert _send(client, ctx, data).status_code == 201
    dup = _send(client, ctx, data)
    assert dup.status_code == 422 and "já foi anexado" in dup.json()["detail"]
    assert _send(client, ctx, make_dicom(seed=1), dentes="99").status_code == 422
    assert _send(client, ctx, make_dicom(seed=2), dentes="a,b").status_code == 422
    assert _send(client, ctx, make_dicom(seed=3), tipo="xpto").status_code == 422


def test_kind_override_update_and_invalidate(client, ctx):
    r = _send(client, ctx, make_dicom(modality="IO"), tipo="interproximal")
    exam = r.json()
    assert exam["kind"] == "interproximal"
    r = client.patch(
        f"/imagens/exames/{exam['id']}",
        json={"teeth": [16, 15], "notes": "Controle"},
        headers=ctx["h"],
    )
    assert r.status_code == 200
    assert r.json()["teeth"] == [15, 16]

    r = client.post(
        f"/imagens/exames/{exam['id']}/invalidar",
        json={"reason": "Paciente errado"},
        headers=ctx["h"],
    )
    assert r.status_code == 200 and r.json()["invalidated_at"]
    base = f"/imagens/pacientes/{ctx['patient']}/exames"
    assert client.get(base, headers=ctx["h"]).json() == []
    assert len(client.get(base, params={"incluir_invalidados": True}, headers=ctx["h"]).json()) == 1
    again = client.patch(f"/imagens/exames/{exam['id']}", json={"notes": "x"}, headers=ctx["h"])
    assert again.status_code == 422


def test_database_guards(client, ctx):
    exam = _send(client, ctx, make_dicom()).json()
    with tenant_session(ctx["clinic"].id) as s:
        s.execute(select(1))
        with pytest.raises(DBAPIError, match="não mudam"):
            s.execute(
                text("UPDATE imaging_exams SET sha256 = repeat('a', 64) WHERE id = :id"),
                {"id": exam["id"]},
            )
    with tenant_session(ctx["clinic"].id) as s:
        s.execute(select(1))
        with pytest.raises(DBAPIError, match="permission denied"):
            s.execute(text("DELETE FROM imaging_exams"))


def test_roles(client, ctx, add_member):
    reception, pw = add_member(ctx["clinic"], Role.RECEPCAO)
    hr = _login(client, reception.email, pw)
    assert _send(client, ctx, make_dicom(), headers=hr).status_code == 403
    base = f"/imagens/pacientes/{ctx['patient']}/exames"
    assert client.get(base, headers=hr).status_code == 403

    asb, pw = add_member(ctx["clinic"], Role.ASB)
    ha = _login(client, asb.email, pw)
    exam = _send(client, ctx, make_dicom(), headers=ha).json()
    r = client.post(f"/imagens/exames/{exam['id']}/invalidar", json={"reason": "teste"}, headers=ha)
    assert r.status_code == 403

    manager, pw = add_member(ctx["clinic"], Role.GESTOR)
    hg = _login(client, manager.email, pw)
    assert client.get(base, headers=hg).status_code == 200
    assert _send(client, ctx, make_dicom(seed=5), headers=hg).status_code == 403


def test_other_clinic_isolated(client, ctx, make_clinic):
    from app.modules.imagens.models import ImagingExam

    exam = _send(client, ctx, make_dicom()).json()
    clinic_b, user_b, pw_b = make_clinic(role=Role.ADMIN)
    hb = _login(client, user_b.email, pw_b)
    assert client.get(f"/imagens/exames/{exam['id']}", headers=hb).status_code == 404
    assert client.get(f"/imagens/exames/{exam['id']}/arquivo", headers=hb).status_code == 404
    assert client.get(f"/imagens/pacientes/{ctx['patient']}/exames", headers=hb).status_code == 404
    assert _send(client, ctx, make_dicom(seed=9), headers=hb).status_code == 404
    with tenant_session(clinic_b.id) as s:
        assert s.scalars(select(ImagingExam)).all() == []
