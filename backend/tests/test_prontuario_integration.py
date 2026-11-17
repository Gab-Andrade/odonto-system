"""Prontuário — anamnese: modelos versionados, respostas imutáveis, alertas, papéis e
isolamento entre clínicas."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.prontuario.models import (
    AnamnesisResponse,
    AnamnesisTemplate,
    AnamnesisTemplateVersion,
)

pytestmark = pytest.mark.integration

M = "/prontuario/anamnese/modelos"
V = "/prontuario/anamnese/versoes"

QUESTIONS = [
    {"id": "alergia", "text": "Tem alergia?", "type": "sim_nao", "required": True, "alert": True},
    {"id": "qual_alergia", "text": "Qual?", "type": "texto", "alert": True},
    {"id": "fuma", "text": "Fuma?", "type": "escolha_unica", "options": ["Sim", "Não"]},
]


def _setup(client, make_clinic, add_member):
    """Clínica com admin, gestor, dentista, ASB e recepção; um paciente."""
    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    headers = {Role.ADMIN: _auth(_login(client, admin.email, pw).json()["access_token"])}
    for role in (Role.GESTOR, Role.DENTISTA, Role.ASB, Role.RECEPCAO):
        user, pw_u = add_member(clinic, role)
        headers[role] = _auth(_login(client, user.email, pw_u).json()["access_token"])
    patient = client.post(
        "/pacientes",
        json={"full_name": "Ana Souza", "phone": "11987654321"},
        headers=headers[Role.RECEPCAO],
    ).json()
    return {"clinic": clinic, "h": headers, "patient": patient["id"]}


def _published_template(client, ctx, name="Anamnese geral", questions=QUESTIONS):
    h = ctx["h"][Role.GESTOR]
    resp = client.post(M, json={"name": name, "questions": questions}, headers=h)
    assert resp.status_code == 201, resp.text
    t = resp.json()
    pub = client.post(f"{V}/{t['draft']['id']}/publicar", headers=h)
    assert pub.status_code == 200, pub.text
    return t["id"], pub.json()["id"]


def _answer(client, ctx, template_id, version_id, answers, role=Role.DENTISTA, expect=201):
    resp = client.post(
        f"/prontuario/pacientes/{ctx['patient']}/anamneses",
        json={"template_id": template_id, "version_id": version_id, "answers": answers},
        headers=ctx["h"][role],
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


def _actions(clinic):
    with tenant_session(clinic.id) as s:
        return [a for (a,) in s.execute(select(AuditLog.action)).all()]


# ---------- modelos e versões ----------


def test_template_versioning_flow(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"][Role.GESTOR]

    t = client.post(M, json={"name": "Geral", "questions": QUESTIONS}, headers=h).json()
    assert t["published"] is None and t["draft"]["number"] == 1
    draft1 = t["draft"]["id"]

    assert client.post(f"{M}/{t['id']}/rascunho", headers=h).status_code == 409  # já tem
    v1 = client.post(f"{V}/{draft1}/publicar", headers=h).json()
    assert v1["status"] == "publicada" and v1["published_at"] is not None

    # Publicada não muda nem é descartada.
    assert client.put(f"{V}/{draft1}", json={"questions": []}, headers=h).status_code == 409
    assert client.delete(f"{V}/{draft1}", headers=h).status_code == 409

    # Novo rascunho copia as perguntas da publicada.
    d2 = client.post(f"{M}/{t['id']}/rascunho", headers=h).json()
    assert d2["number"] == 2 and d2["questions"] == v1["questions"]
    new_q = [*QUESTIONS, {"id": "peso", "text": "Peso", "type": "numero"}]
    put = client.put(f"{V}/{d2['id']}", json={"questions": new_q}, headers=h)
    assert put.status_code == 200 and len(put.json()["questions"]) == 4
    assert client.post(f"{V}/{d2['id']}/publicar", headers=h).status_code == 200

    detail = client.get(f"{M}/{t['id']}", headers=h).json()
    assert detail["published"]["number"] == 2 and detail["draft"] is None
    assert [(v["number"], v["status"]) for v in detail["versions"]] == [
        (2, "publicada"),
        (1, "substituida"),
    ]

    # Rascunho pode ser descartado; o número dele volta a ficar livre.
    d3 = client.post(f"{M}/{t['id']}/rascunho", headers=h).json()
    assert client.delete(f"{V}/{d3['id']}", headers=h).status_code == 204
    assert client.post(f"{M}/{t['id']}/rascunho", headers=h).json()["number"] == 3

    assert {
        "prontuario.modelo_criado",
        "prontuario.versao_publicada",
        "prontuario.rascunho_criado",
        "prontuario.rascunho_alterado",
        "prontuario.rascunho_descartado",
    } <= set(_actions(ctx["clinic"]))


def test_template_rules(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"][Role.ADMIN]
    empty = client.post(M, json={"name": "Vazio"}, headers=h).json()
    resp = client.post(f"{V}/{empty['draft']['id']}/publicar", headers=h)
    assert resp.status_code == 409 and "pergunta" in resp.json()["detail"]

    assert client.post(M, json={"name": "Vazio"}, headers=h).status_code == 409  # nome único
    bad = {"name": "Ruim", "questions": [{"id": "x", "text": "X", "type": "multipla"}]}
    assert client.post(M, json=bad, headers=h).status_code == 422

    patched = client.patch(f"{M}/{empty['id']}", json={"active": False}, headers=h)
    assert patched.status_code == 200 and patched.json()["active"] is False
    assert client.get(M, headers=h).json() == []
    assert len(client.get(M, params={"incluir_inativos": True}, headers=h).json()) == 1
    assert client.patch(f"{M}/{empty['id']}", json={"name": None}, headers=h).status_code == 409


def test_published_questions_are_frozen_in_the_database(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _, version_id = _published_template(client, ctx)
    with tenant_session(ctx["clinic"].id) as s:
        v = s.get(AnamnesisTemplateVersion, uuid.UUID(version_id))
        v.questions = []
        with pytest.raises(IntegrityError, match="não pode ser alterada"):
            s.flush()
    for sql in (
        "DELETE FROM anamnesis_template_versions",
        "UPDATE anamnesis_template_versions SET number = number + 10",
    ):
        with tenant_session(ctx["clinic"].id) as s:
            s.execute(select(1))
            with pytest.raises(IntegrityError, match="não"):
                s.execute(text(sql))


# ---------- respostas ----------


def test_answer_history_current_and_alerts(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    t_id, v1 = _published_template(client, ctx)
    pid = ctx["patient"]

    first = _answer(client, ctx, t_id, v1, {"alergia": True, "qual_alergia": " Dipirona "})
    assert first["current"] is True and first["version_number"] == 1
    assert first["answers"] == {"alergia": True, "qual_alergia": "Dipirona"}
    assert [a["question_id"] for a in first["alerts"]] == ["alergia", "qual_alergia"]

    alerts = client.get(f"/prontuario/pacientes/{pid}/alertas", headers=ctx["h"][Role.ASB]).json()
    assert [(a["question_id"], a["template_name"]) for a in alerts] == [
        ("alergia", "Anamnese geral"),
        ("qual_alergia", "Anamnese geral"),
    ]

    # Publica v2; resposta com a versão antiga (formulário aberto antes) é recusada.
    h = ctx["h"][Role.GESTOR]
    d2 = client.post(f"/prontuario/anamnese/modelos/{t_id}/rascunho", headers=h).json()
    v2 = client.post(f"{V}/{d2['id']}/publicar", headers=h).json()["id"]
    stale = _answer(client, ctx, t_id, v1, {"alergia": False}, expect=409)
    assert "recarregue" in stale["detail"]

    # Nova resposta (pela ASB) vira a atual e zera os alertas do cabeçalho.
    _answer(client, ctx, t_id, v2, {"alergia": False, "fuma": "Não"}, role=Role.ASB)
    history = client.get(f"/prontuario/pacientes/{pid}/anamneses", headers=h).json()
    assert [(r["version_number"], r["current"]) for r in history] == [(2, True), (1, False)]
    assert client.get(f"/prontuario/pacientes/{pid}/alertas", headers=h).json() == []

    # A resposta antiga continua com as perguntas da versão em que foi respondida.
    old = client.get(f"/prontuario/anamneses/{first['id']}", headers=h).json()
    assert old["current"] is False and old["version_id"] == v1
    assert [q["id"] for q in old["questions"]] == [q["id"] for q in QUESTIONS]

    actions = _actions(ctx["clinic"])
    for action in (
        "prontuario.anamnese_registrada",
        "prontuario.anamneses_listadas",
        "prontuario.anamnese_lida",
        "prontuario.alertas_lidos",
    ):
        assert action in actions
    # Auditoria de leitura sem conteúdo clínico: só ids e contagens.
    with tenant_session(ctx["clinic"].id) as s:
        details = s.scalars(
            select(AuditLog.details).where(AuditLog.action.like("prontuario.%"))
        ).all()
    assert all("Dipirona" not in str(d) and "answers" not in str(d) for d in details)


def test_answer_validation(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    t_id, v1 = _published_template(client, ctx)
    resp = _answer(client, ctx, t_id, v1, {"qual_alergia": "x"}, expect=409)
    assert "obrigatória" in resp["detail"]
    _answer(client, ctx, t_id, v1, {"alergia": True, "fuma": "Talvez"}, expect=409)
    _answer(client, ctx, t_id, v1, {"alergia": True, "outra": 1}, expect=409)

    # Modelo desativado ou sem versão publicada não recebe resposta.
    h = ctx["h"][Role.ADMIN]
    draft_only = client.post(M, json={"name": "Só rascunho", "questions": QUESTIONS}, headers=h)
    d = draft_only.json()
    _answer(client, ctx, d["id"], d["draft"]["id"], {"alergia": True}, expect=409)
    client.patch(f"{M}/{t_id}", json={"active": False}, headers=h)
    _answer(client, ctx, t_id, v1, {"alergia": True}, expect=409)

    unknown = str(uuid.uuid4())
    resp = client.post(
        f"/prontuario/pacientes/{unknown}/anamneses",
        json={"template_id": t_id, "version_id": v1, "answers": {}},
        headers=ctx["h"][Role.DENTISTA],
    )
    assert resp.status_code == 404


def test_responses_are_append_only(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    t_id, v1 = _published_template(client, ctx)
    _answer(client, ctx, t_id, v1, {"alergia": True})
    for sql in (
        "UPDATE anamnesis_responses SET answers = '{}'::jsonb",
        "DELETE FROM anamnesis_responses",
    ):
        with tenant_session(ctx["clinic"].id) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))


# ---------- papéis ----------


def test_roles(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    t_id, v1 = _published_template(client, ctx)
    pid = ctx["patient"]
    resp_id = _answer(client, ctx, t_id, v1, {"alergia": False})["id"]
    reads = (
        f"/prontuario/pacientes/{pid}/anamneses",
        f"/prontuario/pacientes/{pid}/alertas",
        f"/prontuario/anamneses/{resp_id}",
        M,
    )

    # Recepção não acessa conteúdo clínico.
    rec = ctx["h"][Role.RECEPCAO]
    for url in reads:
        assert client.get(url, headers=rec).status_code == 403, url
    _answer(client, ctx, t_id, v1, {"alergia": False}, role=Role.RECEPCAO, expect=403)

    # Gestor lê, monta modelos, mas não preenche.
    for url in reads:
        assert client.get(url, headers=ctx["h"][Role.GESTOR]).status_code == 200, url
    _answer(client, ctx, t_id, v1, {"alergia": False}, role=Role.GESTOR, expect=403)

    # ASB e dentista leem e preenchem, mas não montam modelos.
    for role in (Role.ASB, Role.DENTISTA):
        assert client.get(reads[0], headers=ctx["h"][role]).status_code == 200
        _answer(client, ctx, t_id, v1, {"alergia": False}, role=role)
        assert (
            client.post(M, json={"name": f"De {role}"}, headers=ctx["h"][role]).status_code == 403
        )
        assert client.post(f"{M}/{t_id}/rascunho", headers=ctx["h"][role]).status_code == 403


# ---------- isolamento ----------


def test_other_clinic_cannot_see_or_use(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    t_id, v1 = _published_template(client, a)
    resp_id = _answer(client, a, t_id, v1, {"alergia": True})["id"]
    hb = b["h"][Role.ADMIN]

    assert client.get(M, headers=hb).json() == []
    assert client.get(f"{M}/{t_id}", headers=hb).status_code == 404
    assert client.get(f"{V}/{v1}", headers=hb).status_code == 404
    assert client.post(f"{M}/{t_id}/rascunho", headers=hb).status_code == 404
    assert client.patch(f"{M}/{t_id}", json={"name": "X"}, headers=hb).status_code == 404
    assert client.get(f"/prontuario/anamneses/{resp_id}", headers=hb).status_code == 404
    assert (
        client.get(f"/prontuario/pacientes/{a['patient']}/alertas", headers=hb).status_code == 404
    )
    # B não responde no paciente de A, nem no próprio paciente com o modelo de A.
    resp = client.post(
        f"/prontuario/pacientes/{b['patient']}/anamneses",
        json={"template_id": t_id, "version_id": v1, "answers": {"alergia": True}},
        headers=hb,
    )
    assert resp.status_code == 404

    with tenant_session(b["clinic"].id) as s:
        for model in (AnamnesisTemplate, AnamnesisTemplateVersion, AnamnesisResponse):
            assert s.scalar(select(func.count()).select_from(model)) == 0
        # FK composta: B não pendura resposta na versão de A.
        s.add(
            AnamnesisResponse(
                clinic_id=b["clinic"].id,
                patient_id=uuid.UUID(b["patient"]),
                template_id=uuid.UUID(t_id),
                version_id=uuid.UUID(v1),
                answers={},
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
