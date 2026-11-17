"""Visualização 2D/3D: cor por face, prioridade, dente oculto, dente fora da arcada e
comparação (sem banco)."""

import uuid
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.modules.odontograma import visualizacao
from app.modules.odontograma.schemas import StatusCreate


@dataclass
class S:
    code: str
    kind: str
    color: str
    sort_order: int = 0
    display_3d: str = "colorir"
    name: str = "x"
    id: uuid.UUID = None

    def __post_init__(self):
        self.id = uuid.uuid5(uuid.NAMESPACE_DNS, self.code)


CARIE = S("carie", "patologia", "#D32F2F")
RESTAURACAO = S("restauracao", "realizado", "#1565C0")
PLANEJADA = S("restauracao_planejada", "planejado", "#F57C00")
COROA = S("coroa", "realizado", "#0D47A1")
AUSENTE = S("ausente", "patologia", "#616161", display_3d="ocultar")
STATUSES = {s.id: s for s in (CARIE, RESTAURACAO, PLANEJADA, COROA, AUSENTE)}


def _by_tooth(view):
    return {t["tooth"]: t for t in view}


def test_face_colors_and_priority():
    marks = {
        (36, "O", RESTAURACAO.id),
        (36, "O", CARIE.id),  # patologia por cima do realizado
        (36, "M", PLANEJADA.id),
        (11, "O", CARIE.id),
    }
    view = _by_tooth(visualizacao.build([11, 21, 36], marks, STATUSES))
    assert list(view) == [11, 21, 36]
    t36 = view[36]
    assert t36["faces"]["O"]["color"] == CARIE.color
    assert [m["code"] for m in t36["faces"]["O"]["marks"]] == ["carie", "restauracao"]
    assert t36["faces"]["M"]["color"] == PLANEJADA.color
    assert t36["faces"]["V"]["color"] is None and t36["faces"]["V"]["node"] == "36_V"
    assert t36["node"] == "dente_36" and not t36["hidden"] and t36["in_arch"]
    # Rótulo clínico: incisal no anterior, palatina na arcada superior.
    assert set(view[11]["faces"]) == {"M", "D", "I", "V", "P"}
    assert view[11]["faces"]["I"]["face"] == "O" and view[11]["faces"]["I"]["color"]
    assert all(f["color"] is None for f in view[21]["faces"].values())


def test_whole_tooth_paints_faces_and_hides():
    marks = {(16, None, COROA.id), (16, "O", CARIE.id), (18, None, AUSENTE.id)}
    view = _by_tooth(visualizacao.build([16, 18], marks, STATUSES))
    assert view[16]["color"] == COROA.color
    assert view[16]["faces"]["O"]["color"] == CARIE.color  # face marcada vence
    assert view[16]["faces"]["V"]["color"] == COROA.color
    assert view[18]["hidden"] and not view[16]["hidden"]


def test_marked_outside_arch_is_kept():
    view = _by_tooth(visualizacao.build([11], {(55, "O", CARIE.id)}, STATUSES))
    assert view[55]["in_arch"] is False and view[55]["deciduous"]
    assert view[11]["in_arch"]


def test_diff():
    before = {(36, "O", CARIE.id), (11, None, COROA.id)}
    after = {(36, "O", RESTAURACAO.id), (11, None, COROA.id), (46, "M", CARIE.id)}
    added, removed = visualizacao.diff(before, after)
    assert added == [(46, "M", CARIE.id), (36, "O", RESTAURACAO.id)]
    assert removed == [(36, "O", CARIE.id)]


def test_status_display_schema():
    base = {"code": "x", "name": "X", "color": "#123456", "kind": "patologia", "scope": "dente"}
    assert StatusCreate(**base).display_3d == "colorir"
    assert StatusCreate(**base, display_3d="ocultar").display_3d == "ocultar"
    with pytest.raises(ValidationError):
        StatusCreate(**base, display_3d="piscar")
