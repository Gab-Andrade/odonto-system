"""Odontograma: legenda padrão e editável, marcações por lote, odontograma em qualquer
data, papéis, garantias no banco e isolamento entre clínicas."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_auth_integration import _auth, _login

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.core.roles import Role
from app.modules.odontograma.models import OdontogramEvent, ToothStatus
from app.modules.odontograma.regras import DEFAULT_LEGEND

pytestmark = pytest.mark.integration

L = "/odontograma/legenda"


def _setup(client, make_clinic, add_member):
    clinic, admin, pw = make_clinic(role=Role.ADMIN)
    h = {"admin": _auth(_login(client, admin.email, pw).json()["access_token"])}
    for key, role in (
        ("dent", Role.DENTISTA),
        ("asb", Role.ASB),
        ("gestor", Role.GESTOR),
        ("recep", Role.RECEPCAO),
    ):
        user, pw_u = add_member(clinic, role)
        h[key] = _auth(_login(client, user.email, pw_u).json()["access_token"])
    patient = client.post(
        "/pacientes", json={"full_name": "Ana Souza", "phone": "11987654321"}, headers=h["recep"]
    ).json()
    legend = {s["code"]: s["id"] for s in client.get(L, headers=h["asb"]).json()}
    return {"clinic": clinic, "h": h, "patient": patient["id"], "legend": legend}


def _mark(client, ctx, events, who="asb", expect=201, patient=None, **extra):
    body = {"events": events, **extra}
    resp = client.post(
        f"/odontograma/pacientes/{patient or ctx['patient']}/eventos",
        json=body,
        headers=ctx["h"][who],
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


def _ev(ctx, code, tooth, face=None, action="marcar"):
    return {"tooth": tooth, "face": face, "status_id": ctx["legend"][code], "action": action}


def _odontogram(client, ctx, who="dent", **params):
    resp = client.get(
        f"/odontograma/pacientes/{ctx['patient']}", params=params, headers=ctx["h"][who]
    )
    assert resp.status_code == 200, resp.text
    return {
        t["tooth"]: (
            sorted(m["code"] for m in t["whole"]),
            {f: sorted(m["code"] for m in ms) for f, ms in t["faces"].items()},
        )
        for t in resp.json()["teeth"]
    }


# ---------- legenda ----------


def test_default_legend_and_editing(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"]
    assert set(ctx["legend"]) == {row[0] for row in DEFAULT_LEGEND}
    assert len(client.get(L, headers=h["dent"]).json()) == len(DEFAULT_LEGEND)  # idempotente

    item = {"code": "mancha", "name": "Mancha", "color": "#795548", "kind": "patologia",
            "scope": "face"}  # fmt: skip
    created = client.post(L, json=item, headers=h["gestor"])
    assert created.status_code == 201, created.text
    assert client.post(L, json=item, headers=h["admin"]).status_code == 409  # código único
    sid = created.json()["id"]

    # Antes de usar, tipo e escopo mudam; depois, não.
    resp = client.patch(f"{L}/{sid}", json={"kind": "planejado"}, headers=h["admin"])
    assert resp.status_code == 200 and resp.json()["kind"] == "planejado"
    ctx["legend"]["mancha"] = sid
    _mark(client, ctx, [_ev(ctx, "mancha", 21, "V")])
    resp = client.patch(f"{L}/{sid}", json={"scope": "dente"}, headers=h["admin"])
    assert resp.status_code == 409
    resp = client.patch(f"{L}/{sid}", json={"color": "#000000", "name": "Mancha branca"},
                        headers=h["gestor"])  # fmt: skip
    assert resp.status_code == 200 and resp.json()["name"] == "Mancha branca"

    # Só admin e gestor mudam o item para a clínica.
    for who in ("dent", "asb", "recep"):
        resp = client.patch(f"{L}/{sid}", json={"color": "#112233"}, headers=h[who])
        assert resp.status_code == 403
    assert client.post(L, json={**item, "code": "outro"}, headers=h["dent"]).status_code == 403

    # Desativado some da lista padrão e não pode ser marcado; pode ser removido.
    client.patch(f"{L}/{sid}", json={"active": False}, headers=h["admin"])
    assert "mancha" not in {s["code"] for s in client.get(L, headers=h["dent"]).json()}
    listed = client.get(L, params={"incluir_inativos": True}, headers=h["dent"]).json()
    assert "mancha" in {s["code"] for s in listed}
    _mark(client, ctx, [_ev(ctx, "mancha", 22, "V")], expect=409)
    _mark(client, ctx, [_ev(ctx, "mancha", 21, "V", action="remover")])


def test_personal_color_only_for_who_chose(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"]
    carie = ctx["legend"]["carie"]
    _mark(client, ctx, [_ev(ctx, "carie", 36, "O")])
    clinic_color = next(s for s in client.get(L, headers=h["admin"]).json() if s["id"] == carie)
    clinic_color = clinic_color["color"]

    def seen(who):
        legend = {s["id"]: s for s in client.get(L, headers=h[who]).json()}[carie]
        vis = client.get(
            f"/odontograma/pacientes/{ctx['patient']}/visualizacao", headers=h[who]
        ).json()
        face = next(t for t in vis["teeth"] if t["tooth"] == 36)["faces"]["O"]
        flat = client.get(f"/odontograma/pacientes/{ctx['patient']}", headers=h[who]).json()
        mark = next(t for t in flat["teeth"] if t["tooth"] == 36)["faces"]["O"][0]
        assert legend["color"] == face["color"] == mark["color"]
        return legend

    resp = client.put(f"{L}/{carie}/minha-cor", json={"color": "#000000"}, headers=h["dent"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["personal"] is True and resp.json()["clinic_color"] == clinic_color
    mine = seen("dent")
    assert mine["color"] == "#000000" and mine["personal"] is True
    # Os outros continuam vendo a cor da clínica.
    for who in ("admin", "asb"):
        other = seen(who)
        assert other["color"] == clinic_color and other["personal"] is False

    # Admin muda a cor da clínica: vale para todos, menos para quem tem cor pessoal.
    assert (
        client.patch(f"{L}/{carie}", json={"color": "#00FF00"}, headers=h["admin"]).status_code
        == 200
    )
    assert seen("asb")["color"] == "#00FF00"
    assert seen("dent")["color"] == "#000000"

    # Removida, volta para a da clínica; remover de novo não muda nada.
    for _ in range(2):
        resp = client.delete(f"{L}/{carie}/minha-cor", headers=h["dent"])
        assert resp.status_code == 200 and resp.json()["color"] == "#00FF00"
    assert seen("dent")["personal"] is False

    assert (
        client.put(f"{L}/{carie}/minha-cor", json={"color": "preto"}, headers=h["dent"]).status_code
        == 422
    )
    resp = client.put(f"{L}/{uuid.uuid4()}/minha-cor", json={"color": "#000000"}, headers=h["dent"])
    assert resp.status_code == 404
    resp = client.put(f"{L}/{carie}/minha-cor", json={"color": "#000000"}, headers=h["recep"])
    assert resp.status_code == 403

    # Outra clínica não enxerga o item nem a cor pessoal.
    _, admin2, pw2 = make_clinic(role=Role.ADMIN)
    h2 = _auth(_login(client, admin2.email, pw2).json()["access_token"])
    resp = client.put(f"{L}/{carie}/minha-cor", json={"color": "#123456"}, headers=h2)
    assert resp.status_code == 404
    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"odontograma.cor_pessoal_alterada", "odontograma.cor_pessoal_removida"} <= actions


# ---------- anotações por dente ----------


def test_tooth_notes(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"]
    url = f"/odontograma/pacientes/{ctx['patient']}/anotacoes"

    first = client.post(url, json={"tooth": 16, "text": "  Sensível ao frio  "}, headers=h["dent"])
    assert first.status_code == 201, first.text
    assert first.json()["text"] == "Sensível ao frio" and first.json()["created_by"]
    assert (
        client.post(url, json={"tooth": 75, "text": "Mobilidade"}, headers=h["asb"]).status_code
        == 201
    )

    for body, code in (
        ({"tooth": 19, "text": "x"}, 422),  # fora da FDI
        ({"tooth": 16, "text": "   "}, 422),
        ({"tooth": 16, "text": "x" * 2001}, 422),
    ):
        assert client.post(url, json=body, headers=h["dent"]).status_code == code
    for who in ("gestor", "recep"):
        resp = client.post(url, json={"tooth": 16, "text": "x"}, headers=h[who])
        assert resp.status_code == 403

    notes = client.get(url, headers=h["gestor"]).json()
    assert [n["tooth"] for n in notes] == [75, 16]  # mais recente primeiro
    before = client.get(url, params={"em": first.json()["created_at"]}, headers=h["dent"]).json()
    assert [n["tooth"] for n in before] == [16]
    assert client.get(url, headers=h["recep"]).status_code == 403
    missing = f"/odontograma/pacientes/{uuid.uuid4()}/anotacoes"
    assert client.get(missing, headers=h["dent"]).status_code == 404

    # Paciente inativo: lê, mas não recebe anotação nova.
    resp = client.patch(f"/pacientes/{ctx['patient']}", json={"active": False}, headers=h["admin"])
    assert resp.status_code == 200, resp.text
    assert client.post(url, json={"tooth": 11, "text": "x"}, headers=h["dent"]).status_code == 409
    assert len(client.get(url, headers=h["dent"]).json()) == 2

    # Append-only no banco.
    cid = ctx["clinic"].id
    for sql in ("UPDATE tooth_notes SET text = 'x'", "DELETE FROM tooth_notes"):
        with tenant_session(cid) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))

    # Outra clínica não vê nem escreve no paciente.
    _, admin2, pw2 = make_clinic(role=Role.ADMIN)
    h2 = _auth(_login(client, admin2.email, pw2).json()["access_token"])
    assert client.get(url, headers=h2).status_code == 404
    assert client.post(url, json={"tooth": 11, "text": "x"}, headers=h2).status_code == 404
    with tenant_session(cid) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"odontograma.anotacao_criada", "odontograma.anotacoes_lidas"} <= actions


# ---------- marcações ----------


def test_marking_and_odontogram_at_any_date(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    events = _mark(
        client,
        ctx,
        [
            _ev(ctx, "carie", 36, "O"),
            _ev(ctx, "carie", 11, "i"),  # incisal → O
            _ev(ctx, "restauracao_planejada", 16, "P"),  # palatina → L
            _ev(ctx, "ausente", 18),
            _ev(ctx, "carie", 75, "D"),  # decíduo
        ],
    )
    assert [e["face"] for e in events] == ["O", "O", "L", None, "D"]
    assert [e["face_label"] for e in events] == ["O", "I", "P", None, "D"]
    before = datetime.now(UTC)

    _mark(
        client,
        ctx,
        [_ev(ctx, "carie", 36, "O", "remover"), _ev(ctx, "restauracao", 36, "O")],
        who="dent",
    )

    now = _odontogram(client, ctx)
    assert now[36] == ([], {"O": ["restauracao"]})
    assert now[11] == ([], {"I": ["carie"]})
    assert now[16] == ([], {"P": ["restauracao_planejada"]})
    assert now[18] == (["ausente"], {})
    assert now[75] == ([], {"D": ["carie"]})

    then = _odontogram(client, ctx, em=before.isoformat())
    assert then[36] == ([], {"O": ["carie"]})
    empty = _odontogram(client, ctx, em="2000-01-01T00:00:00+00:00")
    assert empty == {}

    hist = client.get(
        f"/odontograma/pacientes/{ctx['patient']}/historico", headers=ctx["h"]["gestor"]
    ).json()
    stamps = [datetime.fromisoformat(e["created_at"]) for e in hist]
    assert len(hist) == 7 and stamps == sorted(stamps, reverse=True)

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"odontograma.marcado", "odontograma.lido", "odontograma.historico_lido"} <= actions


def test_marking_rules(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _mark(client, ctx, [_ev(ctx, "ausente", 18, "O")], expect=409)  # dente inteiro com face
    _mark(client, ctx, [_ev(ctx, "carie", 36)], expect=409)  # por face sem face
    _mark(client, ctx, [_ev(ctx, "carie", 36, "M")])
    _mark(client, ctx, [_ev(ctx, "carie", 36, "M")], expect=409)  # já marcado
    _mark(client, ctx, [_ev(ctx, "carie", 37, "M", "remover")], expect=409)  # não existe
    dup = [_ev(ctx, "carie", 46, "M"), _ev(ctx, "carie", 46, "M")]
    _mark(client, ctx, dup, expect=409)
    _mark(client, ctx, [_ev(ctx, "carie", 19, "M")], expect=422)  # FDI
    _mark(client, ctx, [_ev(ctx, "carie", 36, "X")], expect=422)
    unknown = {"tooth": 36, "face": "D", "status_id": str(uuid.uuid4())}
    _mark(client, ctx, [unknown], expect=404)
    _mark(client, ctx, [], expect=422)

    # O lote é atômico: um erro no meio não grava nada.
    _mark(client, ctx, [_ev(ctx, "carie", 26, "M"), _ev(ctx, "carie", 36, "M")], expect=409)
    assert 26 not in _odontogram(client, ctx)


def test_linked_to_encounter(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    enc = client.post(
        "/prontuario/atendimentos", json={"patient_id": ctx["patient"]}, headers=ctx["h"]["dent"]
    ).json()
    events = _mark(client, ctx, [_ev(ctx, "carie", 36, "O")], encounter_id=enc["id"])
    assert events[0]["encounter_id"] == enc["id"]

    other = client.post(
        "/pacientes", json={"full_name": "José", "phone": "11911112222"}, headers=ctx["h"]["recep"]
    ).json()
    _mark(client, ctx, [_ev(ctx, "carie", 36, "M")], patient=other["id"],
          encounter_id=enc["id"], expect=409)  # fmt: skip
    client.post(f"/prontuario/atendimentos/{enc['id']}/fechar", headers=ctx["h"]["dent"])
    _mark(client, ctx, [_ev(ctx, "carie", 36, "M")], encounter_id=enc["id"], expect=409)
    _mark(client, ctx, [_ev(ctx, "carie", 36, "M")], encounter_id=str(uuid.uuid4()), expect=404)


# ---------- papéis ----------


def test_roles(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    pid = ctx["patient"]
    item = {"code": "x", "name": "X", "color": "#123456", "kind": "patologia", "scope": "dente"}
    for who in ("dent", "asb", "recep"):
        assert client.post(L, json=item, headers=ctx["h"][who]).status_code == 403
    _mark(client, ctx, [_ev(ctx, "ausente", 18)], who="gestor", expect=403)
    _mark(client, ctx, [_ev(ctx, "ausente", 18)], who="recep", expect=403)
    _mark(client, ctx, [_ev(ctx, "ausente", 18)], who="admin")
    _mark(client, ctx, [_ev(ctx, "ausente", 18, action="remover")], who="dent")
    _mark(client, ctx, [_ev(ctx, "ausente", 18)], who="asb")
    for url in (L, f"/odontograma/pacientes/{pid}", f"/odontograma/pacientes/{pid}/historico"):
        assert client.get(url, headers=ctx["h"]["recep"]).status_code == 403, url
        assert client.get(url, headers=ctx["h"]["gestor"]).status_code == 200, url


# ---------- garantias no banco ----------


def test_database_guards(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _mark(client, ctx, [_ev(ctx, "carie", 36, "O")])
    cid = ctx["clinic"].id

    for sql in (
        "UPDATE odontogram_events SET tooth = 37",
        "DELETE FROM odontogram_events",
        "DELETE FROM tooth_statuses",
    ):
        with tenant_session(cid) as s:
            s.execute(select(1))
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(sql))

    with tenant_session(cid) as s:
        s.add(
            OdontogramEvent(
                clinic_id=cid,
                patient_id=uuid.UUID(ctx["patient"]),
                tooth=18,
                face="O",
                status_id=uuid.UUID(ctx["legend"]["ausente"]),
                action="marcar",
            )
        )
        with pytest.raises(IntegrityError, match="escopo"):
            s.flush()

    with tenant_session(cid) as s:
        item = s.get(ToothStatus, uuid.UUID(ctx["legend"]["carie"]))
        item.kind = "realizado"
        with pytest.raises(IntegrityError, match="não mudam"):
            s.flush()


# ---------- isolamento ----------


def test_other_clinic_cannot_see_or_use(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    _mark(client, a, [_ev(a, "carie", 36, "O")])
    hb = b["h"]["admin"]

    for url in (
        f"/odontograma/pacientes/{a['patient']}",
        f"/odontograma/pacientes/{a['patient']}/historico",
    ):
        assert client.get(url, headers=hb).status_code == 404
    resp = client.patch(f"{L}/{a['legend']['carie']}", json={"name": "X"}, headers=hb)
    assert resp.status_code == 404
    _mark(client, b, [_ev(a, "carie", 36, "O")], who="admin", expect=404)  # legenda de A
    _mark(client, b, [_ev(b, "carie", 36, "O")], who="admin", patient=a["patient"], expect=404)

    with tenant_session(b["clinic"].id) as s:
        assert s.scalar(select(func.count()).select_from(OdontogramEvent)) == 0
        assert s.scalar(select(func.count()).select_from(ToothStatus)) == len(DEFAULT_LEGEND)
        # FK composta: B não marca no paciente de A.
        s.add(
            OdontogramEvent(
                clinic_id=b["clinic"].id,
                patient_id=uuid.UUID(a["patient"]),
                tooth=36,
                face="O",
                status_id=uuid.UUID(b["legend"]["carie"]),
                action="marcar",
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        # ...nem usa item da legenda de A no próprio paciente...
        s.add(
            OdontogramEvent(
                clinic_id=b["clinic"].id,
                patient_id=uuid.UUID(b["patient"]),
                tooth=36,
                face="O",
                status_id=uuid.UUID(a["legend"]["carie"]),
                action="marcar",
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
    with tenant_session(b["clinic"].id) as s:
        # ...nem grava linha com o clinic_id de A (WITH CHECK do RLS).
        s.add(
            ToothStatus(
                clinic_id=a["clinic"].id,
                code="intruso",
                name="Intruso",
                color="#000000",
                kind="patologia",
                scope="dente",
            )
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
