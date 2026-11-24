"""Cadastro de equipe: membros, primeiro acesso, convites com código e pedidos de admin."""

import pytest
from sqlalchemy import text

from app.core.roles import Role

pytestmark = pytest.mark.integration

NOVA = "minha-senha-nova"


def _login(client, email, password, clinic_id=None):
    body = {"email": email, "password": password}
    if clinic_id:
        body["clinic_id"] = str(clinic_id)
    return client.post("/auth/login", json=body)


def _token(client, email, password, clinic_id=None):
    resp = _login(client, email, password, clinic_id)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _tenant_sql(owner_engine, clinic_id, sql, **params):
    """SQL como dono, mas dentro da clínica (as tabelas têm FORCE RLS: sem isso o dono
    não vê nada)."""
    with owner_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.clinic_id', :cid, true)"), {"cid": str(clinic_id)}
        )
        return conn.execute(text(sql), params).all()


def _actions(owner_engine, clinic_id):
    rows = _tenant_sql(owner_engine, clinic_id, "SELECT action FROM audit_logs ORDER BY created_at")
    return [r[0] for r in rows]


@pytest.fixture
def clinica(client, make_clinic, add_member):
    """Clínica com dois admins (A e B) e uma dentista."""
    clinic, a, pw = make_clinic(Role.ADMIN)
    b, _ = add_member(clinic, Role.ADMIN)
    d, _ = add_member(clinic, Role.DENTISTA)
    return {
        "clinic": clinic,
        "a": a,
        "b": b,
        "d": d,
        "ha": _token(client, a.email, pw),
        "hb": _token(client, b.email, pw),
        "hd": _token(client, d.email, pw),
        "pw": pw,
    }


# --- Membros e primeiro acesso -----------------------------------------------------


def test_only_admin_manages_team(client, clinica):
    assert client.get("/equipe/membros", headers=clinica["hd"]).status_code == 403
    assert client.get("/equipe/convites", headers=clinica["hd"]).status_code == 403
    novo = {"email": "x@exemplo.com", "full_name": "X", "role": "asb"}
    assert client.post("/equipe/membros", json=novo, headers=clinica["hd"]).status_code == 403
    resp = client.get("/equipe/membros", headers=clinica["ha"])
    assert resp.status_code == 200
    assert {m["role"] for m in resp.json()} == {"admin", "dentista"}


def test_new_member_must_define_own_password(client, clinica, owner_engine):
    body = {"email": " Nova@Exemplo.com ", "full_name": " Ana ", "cro": "SP-1", "role": "asb"}
    resp = client.post("/equipe/membros", json=body, headers=clinica["ha"])
    assert resp.status_code == 201, resp.text
    assert resp.headers["cache-control"] == "no-store"
    data = resp.json()
    assert data["invite"] is None and data["invite_code"] is None
    senha = data["temporary_password"]
    assert len(senha) == 14 and senha.count("-") == 2
    assert data["member"]["email"] == "nova@exemplo.com"
    assert data["member"]["full_name"] == "Ana"

    # Com a senha aleatória não entra: só define a dela.
    bloqueado = _login(client, "nova@exemplo.com", senha)
    assert bloqueado.status_code == 403
    errado = client.post(
        "/auth/primeiro-acesso",
        json={"email": "nova@exemplo.com", "current_password": "x", "new_password": NOVA},
    )
    assert errado.status_code == 401
    ok = client.post(
        "/auth/primeiro-acesso",
        json={"email": "nova@exemplo.com", "current_password": senha, "new_password": NOVA},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["role"] == "asb"
    h = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get("/auth/me", headers=h).status_code == 200
    assert _login(client, "nova@exemplo.com", senha).status_code == 401
    _token(client, "nova@exemplo.com", NOVA)

    acoes = _actions(owner_engine, clinica["clinic"].id)
    assert "equipe.membro_adicionado" in acoes and "auth.senha_definida" in acoes
    detalhes = _tenant_sql(
        owner_engine, clinica["clinic"].id, "SELECT coalesce(details::text, '') FROM audit_logs"
    )
    assert not any(senha in d[0] for d in detalhes)

    again = client.post("/equipe/membros", json=body, headers=clinica["ha"])
    assert again.status_code == 409


def test_members_of_other_clinic_are_invisible(client, clinica, make_clinic):
    _, estranho, _ = make_clinic(Role.ADMIN)
    lista = client.get("/equipe/membros?incluir_inativos=true", headers=clinica["ha"]).json()
    assert str(estranho.id) not in {m["user_id"] for m in lista}
    uid = estranho.id
    assert (
        client.patch(f"/equipe/membros/{uid}", json={"active": False}, headers=clinica["ha"])
    ).status_code == 404
    assert (
        client.post(f"/equipe/membros/{uid}/redefinir-senha", headers=clinica["ha"])
    ).status_code == 404


def test_update_and_deactivate_non_admin(client, clinica, owner_engine):
    d = clinica["d"]
    resp = client.patch(
        f"/equipe/membros/{d.id}",
        json={"role": "gestor", "cro": None, "full_name": "Dra. D"},
        headers=clinica["ha"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "gestor" and resp.json()["full_name"] == "Dra. D"

    off = client.patch(f"/equipe/membros/{d.id}", json={"active": False}, headers=clinica["ha"])
    assert off.json()["active"] is False
    assert client.get("/auth/me", headers=clinica["hd"]).status_code == 401  # corta na hora
    ativos = client.get("/equipe/membros", headers=clinica["ha"]).json()
    assert str(d.id) not in {m["user_id"] for m in ativos}
    todos = client.get("/equipe/membros?incluir_inativos=true", headers=clinica["ha"]).json()
    assert str(d.id) in {m["user_id"] for m in todos}

    on = client.patch(f"/equipe/membros/{d.id}", json={"active": True}, headers=clinica["ha"])
    assert on.json()["active"] is True
    assert _actions(owner_engine, clinica["clinic"].id).count("equipe.membro_alterado") == 3


def test_reset_password_forces_new_one_and_drops_sessions(client, clinica):
    d = clinica["d"]
    resp = client.post(f"/equipe/membros/{d.id}/redefinir-senha", headers=clinica["ha"])
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    temp = resp.json()["temporary_password"]
    assert client.get("/auth/me", headers=clinica["hd"]).status_code == 401  # sessão caiu
    assert _login(client, d.email, clinica["pw"]).status_code == 401
    assert _login(client, d.email, temp).status_code == 403
    ok = client.post(
        "/auth/primeiro-acesso",
        json={"email": d.email, "current_password": temp, "new_password": NOVA},
    )
    assert ok.status_code == 200

    b = clinica["b"]
    assert (
        client.post(f"/equipe/membros/{b.id}/redefinir-senha", headers=clinica["ha"])
    ).status_code == 409  # outro admin
    assert (
        client.post(f"/equipe/membros/{clinica['a'].id}/redefinir-senha", headers=clinica["ha"])
    ).status_code == 409  # a própria


def test_change_own_password_returns_new_token(client, clinica, owner_engine):
    d, pw, h = clinica["d"], clinica["pw"], clinica["hd"]
    outra_sessao = _token(client, d.email, pw)
    errada = client.post(
        "/auth/senha", json={"current_password": "x", "new_password": NOVA}, headers=h
    )
    assert errada.status_code == 403
    curta = client.post(
        "/auth/senha", json={"current_password": pw, "new_password": "curta"}, headers=h
    )
    assert curta.status_code == 422
    igual = client.post("/auth/senha", json={"current_password": pw, "new_password": pw}, headers=h)
    assert igual.status_code == 409

    ok = client.post("/auth/senha", json={"current_password": pw, "new_password": NOVA}, headers=h)
    assert ok.status_code == 200, ok.text
    novo = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get("/auth/me", headers=novo).status_code == 200
    assert client.get("/auth/me", headers=outra_sessao).status_code == 401
    _token(client, d.email, NOVA)
    assert "auth.senha_trocada" in _actions(owner_engine, clinica["clinic"].id)


# --- Convite para e-mail que já tem cadastro ---------------------------------------


def test_existing_email_gets_invite_with_code(client, clinica, make_clinic, owner_engine):
    outra, pessoa, pw = make_clinic(Role.DENTISTA, email="multi@exemplo.com")
    body = {"email": "multi@exemplo.com", "full_name": "Outro Nome", "role": "dentista"}
    resp = client.post("/equipe/membros", json=body, headers=clinica["ha"])
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["member"] is None and data["temporary_password"] is None
    assert data["invite"]["email"] == "multi@exemplo.com"
    assert "full_name" not in data["invite"]  # nome e CRO da pessoa não vazam
    code = data["invite_code"]

    # Ainda não é membro: não entra na clínica nem aparece na equipe.
    assert _login(client, pessoa.email, pw).status_code == 200  # só a clínica de origem
    assert _login(client, pessoa.email, pw, clinic_id=clinica["clinic"].id).status_code == 401
    membros = client.get("/equipe/membros?incluir_inativos=true", headers=clinica["ha"]).json()
    assert str(pessoa.id) not in {m["user_id"] for m in membros}
    assert [c["email"] for c in client.get("/equipe/convites", headers=clinica["ha"]).json()] == [
        "multi@exemplo.com"
    ]
    assert client.post("/equipe/membros", json=body, headers=clinica["ha"]).status_code == 409

    aceitar = {"email": pessoa.email, "password": pw, "code": "errado-123"}
    assert client.post("/auth/vinculos/aceitar", json=aceitar).status_code == 400
    aceitar["password"] = "senha-errada"
    aceitar["code"] = code
    assert client.post("/auth/vinculos/aceitar", json=aceitar).status_code == 401
    aceitar["password"] = pw
    aceitar["code"] = f"  {code.upper()} "  # digitado com espaço e maiúsculas
    assert client.post("/auth/vinculos/aceitar", json=aceitar).status_code == 204
    assert client.post("/auth/vinculos/aceitar", json=aceitar).status_code == 400  # uso único

    assert _login(client, pessoa.email, pw).status_code == 409  # agora escolhe a clínica
    h = _token(client, pessoa.email, pw, clinic_id=clinica["clinic"].id)
    assert client.get("/auth/me", headers=h).json()["role"] == "dentista"
    assert client.get("/equipe/convites", headers=clinica["ha"]).json() == []
    assert "equipe.convite_aceito" in _actions(owner_engine, clinica["clinic"].id)

    # Dados e senha são da pessoa: esta clínica não muda.
    uid = pessoa.id
    nome = client.patch(f"/equipe/membros/{uid}", json={"full_name": "Y"}, headers=clinica["ha"])
    assert nome.status_code == 409
    senha = client.post(f"/equipe/membros/{uid}/redefinir-senha", headers=clinica["ha"])
    assert senha.status_code == 409
    papel = client.patch(f"/equipe/membros/{uid}", json={"role": "gestor"}, headers=clinica["ha"])
    assert papel.status_code == 200
    h_outra = _token(client, pessoa.email, pw, clinic_id=outra.id)
    assert client.get("/auth/me", headers=h_outra).json()["role"] == "dentista"


def test_who_only_knows_the_password_cannot_join_other_clinic(client, clinica, make_clinic):
    """O admin da clínica A cadastrou o e-mail e sabe a senha; a clínica B convida a mesma
    pessoa. Sem o código que B entregou, a senha não basta."""
    criado = client.post(
        "/equipe/membros",
        json={"email": "alvo@exemplo.com", "full_name": "Alvo", "role": "dentista"},
        headers=clinica["ha"],
    ).json()
    client.post(
        "/auth/primeiro-acesso",
        json={
            "email": "alvo@exemplo.com",
            "current_password": criado["temporary_password"],
            "new_password": NOVA,
        },
    )
    clinica_b, admin_b, pw_b = make_clinic(Role.ADMIN)
    hb = _token(client, admin_b.email, pw_b)
    convite = client.post(
        "/equipe/membros",
        json={"email": "alvo@exemplo.com", "full_name": "Alvo", "role": "dentista"},
        headers=hb,
    ).json()
    assert convite["invite_code"]
    assert _login(client, "alvo@exemplo.com", NOVA, clinic_id=clinica_b.id).status_code == 401
    chute = {"email": "alvo@exemplo.com", "password": NOVA, "code": "aaaaa-aaaaa"}
    assert client.post("/auth/vinculos/aceitar", json=chute).status_code == 400
    # Convites de B não aparecem para A, nem o contrário.
    assert client.get("/equipe/convites", headers=clinica["ha"]).json() == []
    iid = convite["invite"]["id"]
    assert client.delete(f"/equipe/convites/{iid}", headers=clinica["ha"]).status_code == 404


def test_renew_and_cancel_invite(client, clinica, make_clinic, owner_engine):
    _, pessoa, pw = make_clinic(Role.DENTISTA)
    body = {"email": pessoa.email, "full_name": "P", "role": "asb"}
    data = client.post("/equipe/membros", json=body, headers=clinica["ha"]).json()
    iid, antigo = data["invite"]["id"], data["invite_code"]

    novo = client.post(f"/equipe/convites/{iid}/novo-codigo", headers=clinica["ha"])
    assert novo.status_code == 200 and novo.json()["email"] == pessoa.email
    aceitar = {"email": pessoa.email, "password": pw, "code": antigo}
    assert client.post("/auth/vinculos/aceitar", json=aceitar).status_code == 400

    # Vencido não vale.
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE membership_invites SET expires_at = now() - interval '1 minute'"))
    aceitar["code"] = novo.json()["invite_code"]
    assert client.post("/auth/vinculos/aceitar", json=aceitar).status_code == 400

    assert client.delete(f"/equipe/convites/{iid}", headers=clinica["ha"]).status_code == 204
    assert client.get("/equipe/convites", headers=clinica["ha"]).json() == []
    assert "equipe.convite_cancelado" in _actions(owner_engine, clinica["clinic"].id)


# --- Administradores ---------------------------------------------------------------


def test_other_admin_cannot_be_demoted_directly(client, clinica):
    b = clinica["b"]
    for body in ({"role": "dentista"}, {"active": False}):
        resp = client.patch(f"/equipe/membros/{b.id}", json=body, headers=clinica["ha"])
        assert resp.status_code == 409
        assert "pedido" in resp.json()["detail"]
    d = clinica["d"]  # promover é direto
    assert (
        client.patch(f"/equipe/membros/{d.id}", json={"role": "admin"}, headers=clinica["ha"])
    ).json()["role"] == "admin"


def test_self_demotion_keeps_one_admin(client, make_clinic, add_member):
    clinic, a, pw = make_clinic(Role.ADMIN)
    ha = _token(client, a.email, pw)
    sozinho = client.patch(f"/equipe/membros/{a.id}", json={"role": "gestor"}, headers=ha)
    assert sozinho.status_code == 409
    assert "pelo menos um administrador" in sozinho.json()["detail"]

    add_member(clinic, Role.ADMIN)
    ok = client.patch(f"/equipe/membros/{a.id}", json={"role": "gestor"}, headers=ha)
    assert ok.status_code == 200
    assert client.get("/equipe/membros", headers=ha).status_code == 403  # vale na hora


def test_demotion_only_with_target_acceptance(client, clinica, add_member, owner_engine):
    b = clinica["b"]
    body = {"user_id": str(b.id), "action": "rebaixar", "new_role": "dentista", "reason": "saiu"}
    resp = client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"])
    assert resp.status_code == 201, resp.text
    req = resp.json()
    assert req["status"] == "pendente" and req["target_name"] == b.full_name
    rid = req["id"]
    assert client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).status_code == 409

    # Nem quem pediu nem um terceiro admin aceitam: só o próprio B.
    c, pw = add_member(clinica["clinic"], Role.ADMIN)
    hc = _token(client, c.email, pw)
    for h in (clinica["ha"], hc):
        assert client.post(f"/equipe/solicitacoes/{rid}/aceitar", headers=h).status_code == 403
        assert client.post(f"/equipe/solicitacoes/{rid}/recusar", headers=h).status_code == 403
    assert client.get("/equipe/solicitacoes", headers=clinica["hd"]).status_code == 403

    ok = client.post(f"/equipe/solicitacoes/{rid}/aceitar", headers=clinica["hb"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "aprovada" and ok.json()["decided_by"] == str(b.id)
    assert client.get("/auth/me", headers=clinica["hb"]).json()["role"] == "dentista"
    assert client.get("/equipe/solicitacoes", headers=clinica["ha"]).json() == []
    acoes = _actions(owner_engine, clinica["clinic"].id)
    assert "equipe.solicitacao_criada" in acoes and "equipe.solicitacao_aceita" in acoes


def test_target_accepts_deactivation(client, clinica):
    b = clinica["b"]
    body = {"user_id": str(b.id), "action": "desativar"}
    rid = client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).json()["id"]
    ok = client.post(f"/equipe/solicitacoes/{rid}/aceitar", headers=clinica["hb"])
    assert ok.status_code == 200, ok.text
    assert client.get("/auth/me", headers=clinica["hb"]).status_code == 401


def test_reject_and_cancel(client, clinica):
    a, b = clinica["a"], clinica["b"]
    body = {"user_id": str(b.id), "action": "desativar"}
    rid = client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).json()["id"]
    assert (
        client.post(f"/equipe/solicitacoes/{rid}/cancelar", headers=clinica["hb"])
    ).status_code == 403  # só quem pediu cancela
    rec = client.post(f"/equipe/solicitacoes/{rid}/recusar", headers=clinica["hb"])
    assert rec.json()["status"] == "recusada"
    assert client.get("/auth/me", headers=clinica["hb"]).json()["role"] == "admin"

    back = {"user_id": str(a.id), "action": "rebaixar", "new_role": "gestor"}
    rid2 = client.post("/equipe/solicitacoes", json=back, headers=clinica["hb"]).json()["id"]
    can = client.post(f"/equipe/solicitacoes/{rid2}/cancelar", headers=clinica["hb"])
    assert can.json()["status"] == "cancelada"
    hist = client.get("/equipe/solicitacoes?somente_pendentes=false", headers=clinica["ha"])
    assert [r["status"] for r in hist.json()] == ["cancelada", "recusada"]


def test_request_validation(client, clinica):
    h = clinica["ha"]
    cases = [
        ({"user_id": str(clinica["b"].id), "action": "rebaixar"}, 422),
        ({"user_id": str(clinica["b"].id), "action": "rebaixar", "new_role": "admin"}, 422),
        ({"user_id": str(clinica["b"].id), "action": "desativar", "new_role": "asb"}, 422),
        ({"user_id": str(clinica["d"].id), "action": "desativar"}, 409),  # não é admin
        ({"user_id": str(clinica["a"].id), "action": "desativar"}, 409),  # a si mesmo
    ]
    for body, code in cases:
        assert client.post("/equipe/solicitacoes", json=body, headers=h).status_code == code, body


def test_expired_request_cannot_be_accepted(client, clinica, owner_engine):
    body = {"user_id": str(clinica["b"].id), "action": "desativar"}
    rid = client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).json()["id"]
    _tenant_sql(
        owner_engine,
        clinica["clinic"].id,
        "UPDATE admin_change_requests SET created_at = now() - interval '8 days' "
        "WHERE id = :id RETURNING id",
        id=rid,
    )
    resp = client.post(f"/equipe/solicitacoes/{rid}/aceitar", headers=clinica["hb"])
    assert resp.status_code == 409 and "expirou" in resp.json()["detail"]
    assert client.get("/equipe/solicitacoes", headers=clinica["ha"]).json() == []
    hist = client.get("/equipe/solicitacoes?somente_pendentes=false", headers=clinica["ha"])
    assert hist.json()[0]["status"] == "expirada"
    assert client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).status_code == 201


def test_requests_are_isolated_by_clinic(client, clinica, make_clinic):
    body = {"user_id": str(clinica["b"].id), "action": "desativar"}
    rid = client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).json()["id"]
    _, intruso, pw = make_clinic(Role.ADMIN)
    hi = _token(client, intruso.email, pw)
    assert client.get("/equipe/solicitacoes", headers=hi).json() == []
    assert client.post(f"/equipe/solicitacoes/{rid}/aceitar", headers=hi).status_code == 404


def test_acceptance_rechecks_requester(client, clinica, add_member):
    b = clinica["b"]
    body = {"user_id": str(b.id), "action": "desativar"}
    rid = client.post("/equipe/solicitacoes", json=body, headers=clinica["ha"]).json()["id"]
    a = clinica["a"]  # quem pediu deixa de ser admin antes do aceite
    assert (
        client.patch(f"/equipe/membros/{a.id}", json={"role": "gestor"}, headers=clinica["ha"])
    ).status_code == 200
    resp = client.post(f"/equipe/solicitacoes/{rid}/aceitar", headers=clinica["hb"])
    assert resp.status_code == 409 and "Quem pediu" in resp.json()["detail"]


def test_first_access_only_with_temporary_password(client, clinica):
    d = clinica["d"]  # tem senha própria
    resp = client.post(
        "/auth/primeiro-acesso",
        json={"email": d.email, "current_password": clinica["pw"], "new_password": NOVA},
    )
    assert resp.status_code == 401
    _token(client, d.email, clinica["pw"])  # a senha não mudou


def test_pending_invite_elsewhere_protects_personal_data(client, clinica, make_clinic):
    """Quem tem convite de outra clínica já não é só desta: a senha e os dados não mudam."""
    d = clinica["d"]
    _, admin_b, pw_b = make_clinic(Role.ADMIN)
    hb = _token(client, admin_b.email, pw_b)
    body = {"email": d.email, "full_name": "D", "role": "dentista"}
    assert client.post("/equipe/membros", json=body, headers=hb).json()["invite_code"]
    h = clinica["ha"]
    assert client.post(f"/equipe/membros/{d.id}/redefinir-senha", headers=h).status_code == 409
    nome = client.patch(f"/equipe/membros/{d.id}", json={"full_name": "Outro"}, headers=h)
    assert nome.status_code == 409


def test_other_admin_personal_data_only_by_themselves(client, clinica):
    b = clinica["b"]
    resp = client.patch(f"/equipe/membros/{b.id}", json={"cro": "X-1"}, headers=clinica["ha"])
    assert resp.status_code == 409
    own = client.patch(f"/equipe/membros/{b.id}", json={"cro": "X-1"}, headers=clinica["hb"])
    assert own.status_code == 200 and own.json()["cro"] == "X-1"
