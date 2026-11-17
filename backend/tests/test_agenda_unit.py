from datetime import UTC, datetime, timedelta

import pytest

from app.modules.agenda import regras
from app.modules.agenda.models import AppointmentStatus as S

T0 = datetime(2027, 3, 10, 13, 0, tzinfo=UTC)


def test_period_rules():
    regras.check_period(T0, T0 + timedelta(minutes=30), is_block=False)
    regras.check_period(T0, T0 + timedelta(days=20), is_block=True)
    for start, end, block in [
        (T0, T0, False),
        (T0, T0 - timedelta(minutes=1), False),
        (T0, T0 + timedelta(hours=13), False),
        (T0, T0 + timedelta(days=40), True),
        (T0.replace(tzinfo=None), T0.replace(tzinfo=None) + timedelta(hours=1), False),
    ]:
        with pytest.raises(regras.RuleError):
            regras.check_period(start, end, is_block=block)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (S.AGENDADO, S.CONFIRMADO),
        (S.AGENDADO, S.CANCELADO),
        (S.CONFIRMADO, S.ATENDIDO),
        (S.CONFIRMADO, S.FALTA),
    ],
)
def test_allowed_transitions(current, new):
    regras.check_transition(current, new, T0, T0 + timedelta(minutes=5))


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (S.CONFIRMADO, S.AGENDADO),
        (S.ATENDIDO, S.CANCELADO),
        (S.FALTA, S.ATENDIDO),
        (S.CANCELADO, S.AGENDADO),
        (S.AGENDADO, S.AGENDADO),
    ],
)
def test_forbidden_transitions(current, new):
    with pytest.raises(regras.RuleError, match="Não é possível"):
        regras.check_transition(current, new, T0, T0 + timedelta(hours=1))


@pytest.mark.parametrize("new", [S.ATENDIDO, S.FALTA])
def test_attended_or_missed_only_after_start(new):
    with pytest.raises(regras.RuleError, match="depois do horário"):
        regras.check_transition(S.AGENDADO, new, T0, T0 - timedelta(minutes=1))


def test_editable():
    assert regras.is_editable(S.AGENDADO) and regras.is_editable(S.CONFIRMADO)
    assert not any(regras.is_editable(s) for s in (S.ATENDIDO, S.FALTA, S.CANCELADO))
