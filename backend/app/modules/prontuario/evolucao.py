"""Regras puras de atendimento e evolução clínica (testáveis sem banco)."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

MAX_BACKDATE = timedelta(days=7)
# Folga para relógios levemente adiantados no cliente.
CLOCK_TOLERANCE = timedelta(minutes=5)
MAX_CONTENT = 20_000


class EvolutionRuleError(ValueError):
    pass


def check_performed_at(performed_at: datetime, now: datetime) -> None:
    """Data do ato clínico: até 7 dias para trás, nunca no futuro."""
    if performed_at.tzinfo is None:
        raise EvolutionRuleError("Informe data e hora com fuso horário.")
    if performed_at > now + CLOCK_TOLERANCE:
        raise EvolutionRuleError("A data do atendimento não pode estar no futuro.")
    if performed_at < now - MAX_BACKDATE:
        raise EvolutionRuleError("Registro retroativo só até 7 dias.")


def content_hash(
    *,
    note_id: uuid.UUID,
    encounter_id: uuid.UUID,
    patient_id: uuid.UUID,
    author_id: uuid.UUID,
    kind: str,
    amends_id: uuid.UUID | None,
    performed_at: datetime,
    content: str,
) -> str:
    """SHA-256 de uma forma canônica do registro (o que a assinatura cobre).

    Recalculável a partir das colunas gravadas, para conferir que nada mudou.
    """
    payload = {
        "amends_id": str(amends_id) if amends_id else None,
        "author_id": str(author_id),
        "content": content,
        "encounter_id": str(encounter_id),
        "kind": str(kind),
        "note_id": str(note_id),
        "patient_id": str(patient_id),
        "performed_at": performed_at.astimezone(UTC).isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
