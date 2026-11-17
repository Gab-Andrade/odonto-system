"""Regras puras da agenda (testáveis sem banco)."""

from datetime import datetime, timedelta

from app.modules.agenda.models import AppointmentStatus as S

MAX_DURATION = timedelta(hours=12)
MAX_BLOCK_DURATION = timedelta(days=31)  # férias, congresso
MAX_LIST_RANGE = timedelta(days=62)

# De → para. Atendido, falta e cancelado são finais.
TRANSITIONS: dict[S, frozenset[S]] = {
    S.AGENDADO: frozenset({S.CONFIRMADO, S.ATENDIDO, S.FALTA, S.CANCELADO}),
    S.CONFIRMADO: frozenset({S.ATENDIDO, S.FALTA, S.CANCELADO}),
    S.ATENDIDO: frozenset(),
    S.FALTA: frozenset(),
    S.CANCELADO: frozenset(),
}

# Só fazem sentido depois do horário marcado.
AFTER_START = frozenset({S.ATENDIDO, S.FALTA})

STATUS_LABEL = {
    S.AGENDADO: "agendado",
    S.CONFIRMADO: "confirmado",
    S.ATENDIDO: "atendido",
    S.FALTA: "falta",
    S.CANCELADO: "cancelado",
}


class RuleError(ValueError):
    pass


def check_period(starts_at: datetime, ends_at: datetime, *, is_block: bool) -> None:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise RuleError("Informe data e hora com fuso horário.")
    if ends_at <= starts_at:
        raise RuleError("O fim precisa ser depois do início.")
    limit = MAX_BLOCK_DURATION if is_block else MAX_DURATION
    if ends_at - starts_at > limit:
        raise RuleError("Duração acima do permitido.")


def check_transition(current: S, new: S, starts_at: datetime, now: datetime) -> None:
    if new not in TRANSITIONS[current]:
        raise RuleError(
            f"Não é possível passar de {STATUS_LABEL[current]} para {STATUS_LABEL[new]}."
        )
    if new in AFTER_START and now < starts_at:
        raise RuleError(f"Só é possível marcar {STATUS_LABEL[new]} depois do horário de início.")


def is_editable(status: S) -> bool:
    """Horário, dentista e cadeira só mudam enquanto o agendamento está em aberto."""
    return status in (S.AGENDADO, S.CONFIRMADO)
