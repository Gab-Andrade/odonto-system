"""Odontograma 3D: biblioteca GLB, visualização sincronizada com o 2D, efeito 3D da
legenda, comparação antes/depois, papéis e isolamento."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_odontograma_integration import L, _ev, _mark, _odontogram, _setup

from app.core.audit import AuditLog
from app.core.db import tenant_session
from app.modules.odontograma import glb

pytestmark = pytest.mark.integration


def _viz(client, ctx, who="dent", **params):
    resp = client.get(
        f"/odontograma/pacientes/{ctx['patient']}/visualizacao", params=params,
        headers=ctx["h"][who],
    )  # fmt: skip
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_library_and_models(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"]
    lib = client.get("/odontograma/3d/biblioteca", headers=h["asb"])
    assert lib.status_code == 200, lib.text
    assert len(lib.json()["teeth"]) == 52 and lib.json()["units"] == "mm"

    resp = client.get("/odontograma/3d/dentes/36.glb", headers=h["dent"])
    assert resp.status_code == 200 and resp.headers["content-type"] == "model/gltf-binary"
    assert glb.read_json(resp.content)["nodes"][0]["name"] == "dente_36"
    etag = resp.headers["etag"]
    cached = client.get(
        "/odontograma/3d/dentes/36.glb", headers=h["dent"] | {"If-None-Match": etag}
    )
    assert cached.status_code == 304
    assert client.get("/odontograma/3d/dentes/19.glb", headers=h["dent"]).status_code == 404

    arch = client.get(
        "/odontograma/3d/arcada.glb", params={"dentes": "16,55,11"}, headers=h["gestor"]
    )
    assert arch.status_code == 200
    assert glb.read_json(arch.content)["nodes"][0]["extras"]["dentes"] == [16, 55, 11]
    bad = client.get("/odontograma/3d/arcada.glb", params={"dentes": "11,51"}, headers=h["dent"])
    assert bad.status_code == 422

    for url in ("/odontograma/3d/biblioteca", "/odontograma/3d/dentes/11.glb"):
        assert client.get(url, headers=h["recep"]).status_code == 403
        assert client.get(url).status_code in (401, 403)


def test_visualization_matches_2d(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    before = datetime.now(UTC)
    _mark(client, ctx, [
        _ev(ctx, "carie", 36, "O"),
        _ev(ctx, "restauracao", 36, "M"),
        _ev(ctx, "coroa", 11),
        _ev(ctx, "ausente", 18),
        _ev(ctx, "carie", 75, "D"),  # decíduo fora da arcada permanente
    ])  # fmt: skip

    viz = _viz(client, ctx)
    assert viz["arch"]["source"] == "padrao" and viz["arch"]["dentition"] == "permanente"
    assert viz["arch_model_url"].startswith("/odontograma/3d/arcada.glb?dentes=18,17,")
    teeth = {t["tooth"]: t for t in viz["teeth"]}
    assert len(teeth) == 33  # 32 da arcada + o decíduo marcado
    assert teeth[75]["in_arch"] is False and teeth[36]["in_arch"]
    assert teeth[18]["hidden"] is True and teeth[17]["hidden"] is False
    assert teeth[36]["faces"]["O"]["color"] == "#D32F2F"
    assert teeth[11]["faces"]["V"]["color"] == teeth[11]["color"]  # coroa pinta as faces
    assert teeth[36]["placement"]["translation"][0] > 0  # lado esquerdo do paciente
    assert {s["code"] for s in viz["legend"]} == {"carie", "restauracao", "coroa", "ausente"}

    # Mesmas marcações que o odontograma 2D.
    flat = _odontogram(client, ctx)
    for tooth, (whole, faces) in flat.items():
        t = teeth[tooth]
        assert sorted(m["code"] for m in t["whole"]) == whole
        assert {f: sorted(m["code"] for m in v["marks"]) for f, v in t["faces"].items()
                if v["marks"]} == faces  # fmt: skip

    # Arcada decídua registrada: posições da arcada menor; o 36 fica fora da arcada.
    client.post(
        f"/odontograma/pacientes/{ctx['patient']}/arcada", json={"dentition": "decidua"},
        headers=ctx["h"]["dent"],
    )  # fmt: skip
    teeth = {t["tooth"]: t for t in _viz(client, ctx)["teeth"]}
    assert teeth[75]["in_arch"] and not teeth[36]["in_arch"]
    assert len([t for t in teeth.values() if t["in_arch"]]) == 20

    old = _viz(client, ctx, em=before.isoformat())
    assert all(not t["whole"] and not any(f["marks"] for f in t["faces"].values())
               for t in old["teeth"])  # fmt: skip
    assert old["arch"]["source"] == "padrao"


def test_comparison(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    _mark(client, ctx, [_ev(ctx, "carie", 36, "O"), _ev(ctx, "carie", 46, "M")])
    middle = datetime.now(UTC)
    _mark(client, ctx, [
        _ev(ctx, "carie", 36, "O", "remover"), _ev(ctx, "restauracao", 36, "O"),
        _ev(ctx, "coroa", 11),
    ], who="dent")  # fmt: skip
    url = f"/odontograma/pacientes/{ctx['patient']}/comparacao"
    resp = client.get(url, params={"de": middle.isoformat()}, headers=ctx["h"]["gestor"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(c["tooth"], c["face"], c["mark"]["code"]) for c in body["added"]] == [
        (11, None, "coroa"), (36, "O", "restauracao"),
    ]  # fmt: skip
    assert [(c["tooth"], c["mark"]["code"]) for c in body["removed"]] == [(36, "carie")]
    assert body["teeth_changed"] == [11, 36]

    later = datetime.now(UTC).isoformat()
    params = {"de": later, "ate": middle.isoformat()}
    assert client.get(url, params=params, headers=ctx["h"]["dent"]).status_code == 422
    assert client.get(url, headers=ctx["h"]["dent"]).status_code == 422  # sem "de"
    assert client.get(url, params={"de": later}, headers=ctx["h"]["recep"]).status_code == 403

    with tenant_session(ctx["clinic"].id) as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert "odontograma.comparado" in actions


def test_legend_display_3d(client, make_clinic, add_member):
    ctx = _setup(client, make_clinic, add_member)
    h = ctx["h"]
    legend = {s["code"]: s for s in client.get(L, headers=h["dent"]).json()}
    assert legend["ausente"]["display_3d"] == "ocultar"
    assert legend["carie"]["display_3d"] == "colorir"

    item = {"code": "extraido", "name": "Extraído", "color": "#424242", "kind": "realizado",
            "scope": "dente", "display_3d": "ocultar"}  # fmt: skip
    created = client.post(L, json=item, headers=h["admin"])
    assert created.status_code == 201 and created.json()["display_3d"] == "ocultar"
    face_item = item | {"code": "x_face", "scope": "face"}
    assert client.post(L, json=face_item, headers=h["admin"]).status_code == 409
    carie = legend["carie"]["id"]
    resp = client.patch(f"{L}/{carie}", json={"display_3d": "ocultar"}, headers=h["gestor"])
    assert resp.status_code == 409
    sid = created.json()["id"]
    _mark(client, ctx, [{"tooth": 46, "status_id": sid}])
    # Efeito 3D é só visual: pode mudar depois de usado.
    resp = client.patch(f"{L}/{sid}", json={"display_3d": "colorir"}, headers=h["gestor"])
    assert resp.status_code == 200 and resp.json()["display_3d"] == "colorir"

    with tenant_session(ctx["clinic"].id) as s:
        s.execute(select(1))
        with pytest.raises(IntegrityError, match="display_3d"):
            s.execute(
                text("UPDATE tooth_statuses SET display_3d = 'ocultar' WHERE id = :id"),
                {"id": carie},
            )


def test_other_clinic_cannot_see(client, make_clinic, add_member):
    a = _setup(client, make_clinic, add_member)
    b = _setup(client, make_clinic, add_member)
    _mark(client, a, [_ev(a, "carie", 36, "O")])
    hb = b["h"]["admin"]
    base = f"/odontograma/pacientes/{a['patient']}"
    assert client.get(f"{base}/visualizacao", headers=hb).status_code == 404
    now = datetime.now(UTC).isoformat()
    assert client.get(f"{base}/comparacao", params={"de": now}, headers=hb).status_code == 404
    assert all(not t["whole"] for t in _viz(client, b)["teeth"])
