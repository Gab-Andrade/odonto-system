"""Importação de planilhas: fluxo via API, permissões e isolamento entre clínicas."""

import io
import uuid

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.precificacao.models import ImportJob, ImportProfile

pytestmark = pytest.mark.integration

CSV_V1 = (
    "Código;Procedimento;Valor;Tempo\n"
    "PROF;Profilaxia;R$ 150,00;30 min\n"
    "REST;Restauração;220,00;45 min\n"
    "CANAL;Canal molar;1.200,00;90 min\n"
).encode("cp1252")

MAP = {"procedure_code": "Código", "description": "Procedimento", "price": "Valor"}


def _admin(client, make_clinic):
    clinic, user, pw = make_clinic(role=Role.ADMIN)
    return clinic, _auth(_login(client, user.email, pw).json()["access_token"])


def _table(client, h, name="Base"):
    resp = client.post("/precificacao/tabelas", json={"name": name}, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(client, h, table_id, content=CSV_V1, filename="tabela.csv", aba=None):
    data = {"table_id": str(table_id)}
    if aba:
        data["aba"] = aba
    return client.post(
        "/precificacao/importacoes",
        files={"arquivo": (filename, content, "text/csv")},
        data=data,
        headers=h,
    )


def _validate(client, h, job_id, **body):
    return client.post(f"/precificacao/importacoes/{job_id}/validar", json=body, headers=h)


def _apply(client, h, job_id, ignorar_erros=False):
    return client.post(
        f"/precificacao/importacoes/{job_id}/aplicar",
        json={"ignorar_erros": ignorar_erros},
        headers=h,
    )


def _items(client, h, table_id, version_id):
    url = f"/precificacao/tabelas/{table_id}/versoes/{version_id}/itens"
    return {i["procedure_code"]: i for i in client.get(url, headers=h).json()}


def _publish(client, h, table_id, version_id):
    url = f"/precificacao/tabelas/{table_id}/versoes/{version_id}/publicar"
    assert client.post(url, json={}, headers=h).status_code == 200


# ---------- fluxo ----------


def test_full_import_flow_then_publish_and_resolve(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)

    up = _upload(client, h, table["id"])
    assert up.status_code == 201, up.text
    job = up.json()
    assert job["status"] == "analisada"
    assert job["detected"]["separador"] == "ponto e vírgula"
    assert job["detected"]["mapeamento_sugerido"]["price"] == "Valor"
    assert len(job["amostra"]) == 3

    val = _validate(client, h, job["id"], extra_columns=["Tempo"])  # usa a sugestão
    assert val.status_code == 200, val.text
    report = val.json()["report"]
    assert report["total_erros"] == 0
    assert report["diferencas"]["novos"] == 3
    assert report["total_avisos"] == 0  # "1.200,00" tem vírgula: não é ambíguo

    applied = _apply(client, h, job["id"])
    assert applied.status_code == 200, applied.text
    version = applied.json()["versao"]
    assert version["status"] == "rascunho" and version["version"] == 1

    items = _items(client, h, table["id"], version["id"])
    assert items["CANAL"]["price"] == "1200.00"
    assert items["PROF"]["custom_fields"] == {"Tempo": "30 min"}

    _publish(client, h, table["id"], version["id"])
    client.post(
        "/precificacao/atribuicoes",
        json={"table_id": table["id"], "scope_type": "clinica"},
        headers=h,
    )
    resolved = client.post(
        "/precificacao/resolver", json={"procedure_code": "REST"}, headers=h
    ).json()
    assert resolved["price"] == "220.00"


def test_second_import_shows_diff_and_creates_new_draft(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    job = _upload(client, h, table["id"]).json()
    _validate(client, h, job["id"], column_map=MAP)
    v1 = _apply(client, h, job["id"]).json()["versao"]
    _publish(client, h, table["id"], v1["id"])

    v2_csv = (
        "Código;Procedimento;Valor\n"
        "PROF;Profilaxia;160,00\nREST;Restauração;220,00\nIMPL;Implante;3500\n"
    )
    job2 = _upload(client, h, table["id"], v2_csv.encode()).json()
    diff = _validate(client, h, job2["id"], column_map=MAP).json()["report"]["diferencas"]
    assert (diff["novos"], diff["alterados"], diff["removidos"], diff["inalterados"]) == (
        1,
        1,
        1,
        1,
    )
    assert diff["detalhe"]["removidos"] == ["CANAL"]
    assert diff["detalhe"]["alterados"][0]["mudancas"][0] == {
        "campo": "price",
        "antes": "150.00",
        "depois": "160.00",
    }

    v2 = _apply(client, h, job2["id"]).json()["versao"]
    assert v2["version"] == 2 and v2["status"] == "rascunho"
    assert set(_items(client, h, table["id"], v2["id"])) == {"PROF", "REST", "IMPL"}
    # A versão publicada não mudou.
    assert set(_items(client, h, table["id"], v1["id"])) == {"PROF", "REST", "CANAL"}


def test_errors_block_apply_unless_ignored(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    bad = "Código;Procedimento;Valor\nA;Item A;10\n;Sem código;20\nB;Item B;abc\n".encode()
    job = _upload(client, h, table["id"], bad).json()
    report = _validate(client, h, job["id"], column_map=MAP).json()["report"]
    assert report["total_erros"] == 2
    assert [e["linha"] for e in report["erros"]] == [3, 4]

    assert _apply(client, h, job["id"]).status_code == 409
    applied = _apply(client, h, job["id"], ignorar_erros=True)
    assert applied.status_code == 200
    assert set(_items(client, h, table["id"], applied.json()["versao"]["id"])) == {"A"}
    # Importação aplicada não é aplicada de novo.
    assert _apply(client, h, job["id"], ignorar_erros=True).status_code == 409


def test_apply_requires_revalidation_if_table_changed(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    job1 = _upload(client, h, table["id"]).json()
    job2 = _upload(client, h, table["id"]).json()
    _validate(client, h, job1["id"], column_map=MAP)
    _validate(client, h, job2["id"], column_map=MAP)
    v1 = _apply(client, h, job1["id"]).json()["versao"]
    _publish(client, h, table["id"], v1["id"])
    # job2 foi validado contra "nenhuma versão"; agora existe a v1 publicada.
    assert _apply(client, h, job2["id"]).status_code == 409
    _validate(client, h, job2["id"], column_map=MAP)
    assert _apply(client, h, job2["id"]).status_code == 200


def test_invalid_file_and_mapping(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    assert _upload(client, h, table["id"], b"x", filename="t.xls").status_code == 409
    job = _upload(client, h, table["id"]).json()
    resp = _validate(client, h, job["id"], column_map={"procedure_code": "Código"})
    assert resp.status_code == 409 and "Descrição" in resp.json()["detail"]


def test_profiles(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    other_headers = b"COD;DESCR;VLR;OBS\nX1;Item;99,90;nota\n"
    profile_map = {"procedure_code": "COD", "description": "DESCR", "price": "VLR"}
    resp = client.post(
        "/precificacao/perfis-importacao",
        json={"name": "Planilha do contador", "column_map": profile_map, "extra_columns": ["OBS"]},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    profile = resp.json()
    dup = client.post(
        "/precificacao/perfis-importacao",
        json={"name": "planilha do contador", "column_map": profile_map},
        headers=h,
    )
    assert dup.status_code == 409

    job = _upload(client, h, table["id"], other_headers).json()
    report = _validate(client, h, job["id"], profile_id=profile["id"]).json()
    assert report["column_map"] == profile_map and report["extra_columns"] == ["OBS"]
    assert report["report"]["linhas_validas"] == 1

    url = f"/precificacao/perfis-importacao/{profile['id']}"
    assert client.delete(url, headers=h).status_code == 204
    assert client.get("/precificacao/perfis-importacao", headers=h).json() == []


def test_export_and_template(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    job = _upload(client, h, table["id"]).json()
    _validate(client, h, job["id"], column_map=MAP, extra_columns=["Tempo"])
    version = _apply(client, h, job["id"]).json()["versao"]

    url = f"/precificacao/tabelas/{table['id']}/versoes/{version['id']}/exportar"
    resp = client.get(url, headers=h)
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(resp.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("Código", "Descrição", "Categoria", "Preço", "Tempo")
    assert ("CANAL", "Canal molar", None, 1200, "90 min") in rows

    # O arquivo exportado volta pela importação sem erro.
    job2 = _upload(client, h, table["id"], resp.content, filename="export.xlsx").json()
    report = _validate(client, h, job2["id"], extra_columns=["Tempo"]).json()["report"]
    assert report["total_erros"] == 0 and report["diferencas"]["inalterados"] == 3

    assert client.get("/precificacao/importacoes/modelo", headers=h).status_code == 200


def test_audit(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    job = _upload(client, h, table["id"]).json()
    _validate(client, h, job["id"], column_map=MAP)
    _apply(client, h, job["id"])
    actions = {r["action"]: r for r in client.get("/auditoria", headers=h).json()}
    assert actions["precificacao.importacao_criada"]["details"]["linhas"] == 3
    assert len(actions["precificacao.importacao_criada"]["details"]["sha256"]) == 64
    assert "precificacao.importacao_validada" in actions
    assert "precificacao.importacao_aplicada" in actions


# ---------- permissões ----------


@pytest.mark.parametrize("role", [Role.DENTISTA, Role.RECEPCAO, Role.ASB])
def test_only_managers_import(client, make_clinic, add_member, role):
    clinic, h = _admin(client, make_clinic)
    table = _table(client, h)
    job = _upload(client, h, table["id"]).json()
    user, pw = add_member(clinic, role)
    hr = _auth(_login(client, user.email, pw).json()["access_token"])

    assert _upload(client, hr, table["id"]).status_code == 403
    assert client.get(f"/precificacao/importacoes/{job['id']}", headers=hr).status_code == 403
    assert _validate(client, hr, job["id"], column_map=MAP).status_code == 403
    assert _apply(client, hr, job["id"]).status_code == 403
    assert client.get("/precificacao/perfis-importacao", headers=hr).status_code == 403
    assert client.get("/precificacao/importacoes/modelo", headers=hr).status_code == 403


# ---------- isolamento entre clínicas ----------


def test_other_clinic_cannot_touch_imports(client, make_clinic):
    _, h_a = _admin(client, make_clinic)
    _, h_b = _admin(client, make_clinic)
    table_a = _table(client, h_a)
    job = _upload(client, h_a, table_a["id"]).json()
    profile = client.post(
        "/precificacao/perfis-importacao",
        json={"name": "P", "column_map": MAP},
        headers=h_a,
    ).json()

    assert _upload(client, h_b, table_a["id"]).status_code == 404  # tabela de A
    assert client.get(f"/precificacao/importacoes/{job['id']}", headers=h_b).status_code == 404
    assert _validate(client, h_b, job["id"], column_map=MAP).status_code == 404
    assert _apply(client, h_b, job["id"]).status_code == 404
    assert client.get("/precificacao/importacoes", headers=h_b).json() == []
    assert client.get("/precificacao/perfis-importacao", headers=h_b).json() == []
    url = f"/precificacao/perfis-importacao/{profile['id']}"
    assert client.delete(url, headers=h_b).status_code == 404

    # B não usa perfil de A numa importação própria.
    table_b = _table(client, h_b)
    job_b = _upload(client, h_b, table_b["id"]).json()
    assert _validate(client, h_b, job_b["id"], profile_id=profile["id"]).status_code == 404


def test_rls_and_composite_fk_on_import_tables(client, make_clinic):
    clinic_a, h_a = _admin(client, make_clinic)
    clinic_b, _, _ = make_clinic()
    table_a = _table(client, h_a)
    _upload(client, h_a, table_a["id"])
    client.post(
        "/precificacao/perfis-importacao", json={"name": "P", "column_map": MAP}, headers=h_a
    )

    for model in (ImportJob, ImportProfile):
        with tenant_session(clinic_a.id) as s:
            assert s.scalars(select(model)).all() != []
        with tenant_session(clinic_b.id) as s:
            assert s.scalars(select(model)).all() == []

    def job(clinic_id):
        return ImportJob(
            clinic_id=clinic_id,
            table_id=uuid.UUID(table_a["id"]),
            filename="x.csv",
            file_size=1,
            file_sha256="0" * 64,
            detected={},
            headers=[],
            rows=[],
        )

    with tenant_session(clinic_b.id) as s:
        s.add(job(clinic_b.id))
        with pytest.raises(IntegrityError, match="fk_import_jobs_table_same_clinic"):
            s.commit()
    with tenant_session(clinic_b.id) as s:
        s.add(job(clinic_a.id))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.commit()
    with tenant_session(clinic_b.id) as s:
        s.add(ImportProfile(clinic_id=clinic_a.id, name="X", column_map=MAP, extra_columns=[]))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.commit()


# ---------- revisão: concorrência, retenção e isolamento da exportação ----------


def test_draft_edited_between_validate_and_apply_requires_revalidation(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    versions = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h).json()
    draft = versions[0]  # rascunho v1 criado junto com a tabela
    job = _upload(client, h, table["id"]).json()
    _validate(client, h, job["id"], column_map=MAP)

    # Outra pessoa edita o mesmo rascunho (mesmo id de versão).
    url = f"/precificacao/tabelas/{table['id']}/versoes/{draft['id']}/itens"
    manual = [{"procedure_code": "MANUAL", "description": "Lançado à mão", "price": "10.00"}]
    assert client.put(url, json={"items": manual}, headers=h).status_code == 200

    assert _apply(client, h, job["id"]).status_code == 409
    assert set(_items(client, h, table["id"], draft["id"])) == {"MANUAL"}  # nada apagado
    diff = _validate(client, h, job["id"], column_map=MAP).json()["report"]["diferencas"]
    assert diff["removidos"] == 1  # agora o relatório mostra que MANUAL sairia
    assert _apply(client, h, job["id"]).status_code == 200


def test_rows_are_discarded_after_apply(client, make_clinic):
    _, h = _admin(client, make_clinic)
    table = _table(client, h)
    job = _upload(client, h, table["id"]).json()
    _validate(client, h, job["id"], column_map=MAP)
    _apply(client, h, job["id"])
    after = client.get(f"/precificacao/importacoes/{job['id']}", headers=h).json()
    assert after["status"] == "aplicada" and after["amostra"] == []
    assert after["report"]["linhas_validas"] == 3  # o relatório continua


def test_other_clinic_cannot_export(client, make_clinic):
    _, h_a = _admin(client, make_clinic)
    _, h_b = _admin(client, make_clinic)
    table = _table(client, h_a)
    v1 = client.get(f"/precificacao/tabelas/{table['id']}/versoes", headers=h_a).json()[0]
    url = f"/precificacao/tabelas/{table['id']}/versoes/{v1['id']}/exportar"
    assert client.get(url, headers=h_a).status_code == 200
    assert client.get(url, headers=h_b).status_code == 404


def test_applied_version_fk_is_per_clinic(client, make_clinic):
    _, h_a = _admin(client, make_clinic)
    clinic_b, h_b = _admin(client, make_clinic)
    table_a = _table(client, h_a, "A")
    version_a = client.get(f"/precificacao/tabelas/{table_a['id']}/versoes", headers=h_a).json()[0]
    table_b = _table(client, h_b, "B")
    job_b = _upload(client, h_b, table_b["id"]).json()

    with tenant_session(clinic_b.id) as s:
        job = s.get(ImportJob, uuid.UUID(job_b["id"]))
        job.applied_version_id = uuid.UUID(version_a["id"])
        with pytest.raises(IntegrityError, match="fk_import_jobs_version_same_clinic"):
            s.commit()
