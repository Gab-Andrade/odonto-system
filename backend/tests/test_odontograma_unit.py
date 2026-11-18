"""Odontograma: numeração FDI, faces, reconstrução e validação de lote (sem banco)."""

import uuid

import pytest
from pydantic import ValidationError

from app.modules.odontograma.regras import (
    DEFAULT_LEGEND,
    ROOT_ITEMS,
    Event,
    OdontogramRuleError,
    check_batch,
    face_label,
    is_valid_tooth,
    normalize_face,
    rebuild,
)
from app.modules.odontograma.schemas import EventIn, StatusCreate

CARIE = uuid.UUID(int=1)
RESTAURACAO = uuid.UUID(int=2)


def test_fdi_numbering():
    valid = [q * 10 + p for q in range(1, 5) for p in range(1, 9)]
    valid += [q * 10 + p for q in range(5, 9) for p in range(1, 6)]
    assert len(valid) == 52
    assert all(is_valid_tooth(t) for t in valid)
    invalid = {t for t in range(0, 100)} - set(valid)
    assert not any(is_valid_tooth(t) for t in invalid)  # 10, 19, 56, 90...


def test_face_normalization_and_labels():
    assert (
        normalize_face("i") == "O" and normalize_face("P") == "L" and normalize_face(None) is None
    )
    with pytest.raises(OdontogramRuleError):
        normalize_face("X")
    assert face_label(11, "O") == "I"  # incisal no anterior
    assert face_label(16, "O") == "O"
    assert face_label(16, "L") == "P"  # palatina na arcada superior
    assert face_label(46, "L") == "L"  # lingual na inferior
    assert face_label(53, "O") == "I" and face_label(63, "L") == "P"


def test_schema_validation():
    assert EventIn(tooth=36, face="o", status_id=CARIE).face == "O"
    for bad in ({"tooth": 19}, {"tooth": 56}, {"tooth": 36, "face": "Z"}):
        with pytest.raises(ValidationError):
            EventIn(status_id=CARIE, **bad)
    item = StatusCreate(code="x", name="X", color="#aabbcc", kind="patologia", scope="face")
    assert item.color == "#AABBCC"
    with pytest.raises(ValidationError):
        StatusCreate(code="X Y", name="X", color="red", kind="patologia", scope="face")


def test_rebuild_applies_events_in_order():
    events = [
        Event(36, "O", CARIE, "marcar"),
        Event(36, "O", RESTAURACAO, "marcar"),
        Event(36, "O", CARIE, "remover"),
        Event(11, None, CARIE, "marcar"),
    ]
    assert rebuild(events) == {(36, "O", RESTAURACAO), (11, None, CARIE)}
    assert rebuild(events[:1]) == {(36, "O", CARIE)}


def test_check_batch():
    current = {(36, "O", CARIE)}
    check_batch(current, [Event(36, "O", CARIE, "remover"), Event(36, "M", CARIE, "marcar")])
    for changes in (
        [Event(36, "O", CARIE, "marcar")],  # já marcado
        [Event(36, "M", CARIE, "remover")],  # não existe
        [Event(37, "O", CARIE, "marcar"), Event(37, "O", CARIE, "marcar")],  # repetido
    ):
        with pytest.raises(OdontogramRuleError):
            check_batch(current, changes)


def test_default_legend_is_consistent():
    codes = [row[0] for row in DEFAULT_LEGEND]
    assert len(codes) == len(set(codes))
    for code, name, color, kind, scope in DEFAULT_LEGEND:
        StatusCreate(code=code, name=name, color=color, kind=kind, scope=scope)
    # Itens da raiz são de dente inteiro (a raiz não tem faces).
    scopes = {row[0]: row[4] for row in DEFAULT_LEGEND}
    assert ROOT_ITEMS <= set(scopes) and all(scopes[c] == "dente" for c in ROOT_ITEMS)
