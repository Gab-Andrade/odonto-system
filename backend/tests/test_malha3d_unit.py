"""Biblioteca 3D: GLB válido, nomes dos nós, orientação na arcada e malhas fechadas com os
triângulos para fora (sem banco)."""

import struct

import pytest
from fastapi import HTTPException

from app.modules.odontograma import arcada, glb, malha3d
from app.modules.odontograma.biblioteca_router import parse_teeth
from app.modules.odontograma.regras import FACES

ALL = arcada.ALL_PERMANENT + arcada.ALL_DECIDUOUS


def _rotate(q, v):
    x, y, z, w = q
    # v' = v + 2w(q×v) + 2 q×(q×v)
    cx = (y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0])
    cc = (y * cx[2] - z * cx[1], z * cx[0] - x * cx[2], x * cx[1] - y * cx[0])
    return tuple(v[i] + 2 * w * cx[i] + 2 * cc[i] for i in range(3))


def _accessor(data: bytes, gltf: dict, index: int):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    json_len = struct.unpack_from("<I", data, 12)[0]
    start = 20 + json_len + 8 + view["byteOffset"]
    fmt = {5126: "f", 5123: "H", 5125: "I"}[acc["componentType"]]
    width = 3 if acc["type"] == "VEC3" else 1
    values = struct.unpack_from(f"<{acc['count'] * width}{fmt}", data, start)
    if width == 3:
        return [values[i : i + 3] for i in range(0, len(values), 3)]
    return list(values)


def _triangles(data: bytes, gltf: dict, mesh_index: int):
    prim = gltf["meshes"][mesh_index]["primitives"][0]
    pos = _accessor(data, gltf, prim["attributes"]["POSITION"])
    idx = _accessor(data, gltf, prim["indices"])
    return [(pos[idx[i]], pos[idx[i + 1]], pos[idx[i + 2]]) for i in range(0, len(idx), 3)]


def _signed_volume(triangles) -> float:
    total = 0.0
    for a, b, c in triangles:
        total += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6
    return total


@pytest.mark.parametrize("tooth", [11, 13, 14, 16, 21, 26, 31, 36, 38, 44, 48, 51, 55, 65, 75, 83])
def test_tooth_glb_structure(tooth):
    data = malha3d.tooth_glb(tooth)
    assert data[:4] == b"glTF" and struct.unpack_from("<I", data, 8)[0] == len(data)
    assert len(data) % 4 == 0
    gltf = glb.read_json(data)
    names = [n["name"] for n in gltf["nodes"]]
    assert names[0] == f"dente_{tooth}"
    assert names[1:] == [f"{tooth}_{f}" for f in FACES] + [f"{tooth}_raiz"]
    assert gltf["nodes"][0]["extras"]["fdi"] == tooth
    labels = {n["extras"]["face"]: n["extras"]["rotulo"] for n in gltf["nodes"][1:6]}
    upper, anterior = arcada.is_upper(tooth), tooth % 10 <= 3
    assert labels["O"] == ("I" if anterior else "O")
    assert labels["L"] == ("P" if upper else "L")

    # min/max dos accessors batem com os dados; a coroa (5 faces + colo) é fechada e tem os
    # triângulos para fora (volume com sinal positivo), espelhada ou não.
    crown = []
    for i, mesh in enumerate(gltf["meshes"]):
        prim = mesh["primitives"][0]
        acc = gltf["accessors"][prim["attributes"]["POSITION"]]
        pos = _accessor(data, gltf, prim["attributes"]["POSITION"])
        assert acc["min"] == [min(p[k] for p in pos) for k in range(3)]
        assert acc["max"] == [max(p[k] for p in pos) for k in range(3)]
        assert max(_accessor(data, gltf, prim["indices"])) < len(pos)
        tris = _triangles(data, gltf, i)
        if i < len(FACES):
            crown += tris
        else:
            assert _signed_volume(tris) > 0  # raízes também para fora
    shape = malha3d.shape(tooth)
    box = shape.width * shape.depth * shape.crown
    assert 0.3 * box < _signed_volume(crown + _triangles(data, gltf, len(FACES))) < 1.2 * box


def test_deterministic_output():
    malha3d.tooth_glb.cache_clear()
    first = malha3d.tooth_glb(36)
    malha3d.tooth_glb.cache_clear()
    assert malha3d.tooth_glb(36) == first


@pytest.mark.parametrize("tooth", ALL)
def test_placement_orientation(tooth):
    p = malha3d.placement(tooth)
    x, y, z = p.translation
    q = p.rotation
    assert abs(sum(c * c for c in q) - 1) < 1e-9  # rotação pura
    left = tooth // 10 in (2, 3, 6, 7)
    assert (x > 0) == left
    upper = arcada.is_upper(tooth)
    assert (y > 0) == upper
    occlusal = _rotate(q, (0, 1, 0))
    assert occlusal[1] == pytest.approx(-1 if upper else 1)
    vestibular = _rotate(q, (0, 0, 1))
    # Para fora da arcada: mesmo sentido da posição em x (atrás) e para a frente (+Z).
    assert vestibular[2] > -0.05 or vestibular[0] * x > 0
    assert vestibular[0] * x >= -1e-9
    mesial = _rotate(q, (p.mesial_x, 0, 0))
    assert mesial[0] * x < 0  # aponta para a linha média


def test_arch_symmetry_and_order():
    for right, left in ((11, 21), (16, 26), (48, 38), (55, 65), (83, 73)):
        a, b = malha3d.placement(right).translation, malha3d.placement(left).translation
        assert a[0] == pytest.approx(-b[0]) and a[1:] == pytest.approx(b[1:])
    # Mais para trás quanto maior a posição; decíduo na vaga do sucessor.
    zs = [malha3d.placement(10 + p).translation[2] for p in range(1, 9)]
    assert zs == sorted(zs, reverse=True)
    assert malha3d.placement(55).translation[0] == pytest.approx(
        malha3d.placement(15).translation[0]
    )
    assert abs(malha3d.placement(55, True).translation[0]) < abs(
        malha3d.placement(55).translation[0]
    )


def test_arch_glb_and_library():
    teeth = tuple(arcada.preset("mista"))
    gltf = glb.read_json(malha3d.arch_glb(teeth))
    root = gltf["nodes"][gltf["scenes"][0]["nodes"][0]]
    assert root["name"] == "arcada" and root["extras"]["dentes"] == list(teeth)
    tooth_nodes = [gltf["nodes"][i] for i in root["children"]]
    assert [n["name"] for n in tooth_nodes] == [f"dente_{t}" for t in teeth]
    assert all("translation" in n and "rotation" in n for n in tooth_nodes)

    lib = malha3d.library()
    assert len(lib) == 52 and lib[0]["fdi"] == 18
    by_fdi = {e["fdi"]: e for e in lib}
    assert by_fdi[13]["kind"] == "canino" and by_fdi[14]["kind"] == "pre_molar"
    assert by_fdi[54]["kind"] == "molar" and "placement_deciduous_arch" in by_fdi[54]
    assert "placement_deciduous_arch" not in by_fdi[14]
    assert by_fdi[11]["face_labels"] == {"M": "M", "D": "D", "O": "I", "V": "V", "L": "P"}


def test_invalid_tooth_and_parse():
    with pytest.raises(ValueError):
        malha3d.tooth_glb(19)
    assert len(parse_teeth(None)) == 32
    assert parse_teeth("51, 52") == [52, 51]
    assert parse_teeth("16,55,11") == [16, 55, 11]  # mista deduzida
    for raw in ("11,x", "19", "11,11", "", "11,51,16"):  # 11 e 51: mesma vaga
        with pytest.raises(HTTPException):
            parse_teeth(raw)
