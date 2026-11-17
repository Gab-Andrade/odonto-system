"""Atendimento e evolução: data do ato clínico e hash do conteúdo (sem banco)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.modules.prontuario.evolucao import EvolutionRuleError, check_performed_at, content_hash

NOW = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "delta",
    [timedelta(0), -timedelta(days=7), -timedelta(days=3), timedelta(minutes=4)],
)
def test_performed_at_accepted(delta):
    check_performed_at(NOW + delta, NOW)


@pytest.mark.parametrize(
    "value",
    [
        NOW - timedelta(days=7, seconds=1),
        NOW + timedelta(minutes=6),
        NOW.replace(tzinfo=None),
    ],
)
def test_performed_at_rejected(value):
    with pytest.raises(EvolutionRuleError):
        check_performed_at(value, NOW)


def _hash(**overrides):
    fields = {
        "note_id": uuid.UUID(int=1),
        "encounter_id": uuid.UUID(int=2),
        "patient_id": uuid.UUID(int=3),
        "author_id": uuid.UUID(int=4),
        "kind": "evolucao",
        "amends_id": None,
        "performed_at": NOW,
        "content": "Restauração classe II no 36.",
        **overrides,
    }
    return content_hash(**fields)


def test_hash_is_stable_and_timezone_independent():
    same_instant = NOW.astimezone(timezone(timedelta(hours=-3)))
    assert _hash() == _hash(performed_at=same_instant)
    assert len(_hash()) == 64 and _hash() == _hash()


@pytest.mark.parametrize(
    "change",
    [
        {"content": "Restauração classe II no 37."},
        {"author_id": uuid.UUID(int=5)},
        {"performed_at": NOW + timedelta(seconds=1)},
        {"kind": "adendo", "amends_id": uuid.UUID(int=9)},
        {"note_id": uuid.UUID(int=6)},
    ],
)
def test_hash_changes_with_any_field(change):
    assert _hash(**change) != _hash()
