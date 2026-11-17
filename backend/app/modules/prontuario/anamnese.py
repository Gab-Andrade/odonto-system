"""Regras puras da anamnese (testáveis sem banco).

Uma pergunta é um dict com: `id` (slug), `text`, `type`, `required`, `alert` e,
opcionalmente, `section`, `help`, `options` (escolhas) e `alert_options`.

Quando uma resposta vira alerta (só para perguntas com `alert`):
- sim_nao: resposta "sim" (true);
- escolha_unica / multipla: se `alert_options` foi definido, quando alguma opção marcada
  está nele; senão, qualquer opção marcada;
- texto, número e data: qualquer resposta preenchida.
"""

import math
import re
from datetime import date
from enum import StrEnum
from typing import Any

MAX_QUESTIONS = 150
MAX_OPTIONS = 50
MAX_TEXT_ANSWER = 2000
MAX_NUMBER = 1_000_000_000
QUESTION_ID = re.compile(r"^[a-z0-9_]{1,40}$")


class QuestionType(StrEnum):
    TEXTO = "texto"
    SIM_NAO = "sim_nao"
    ESCOLHA_UNICA = "escolha_unica"
    MULTIPLA = "multipla"
    NUMERO = "numero"
    DATA = "data"


CHOICE_TYPES = frozenset({QuestionType.ESCOLHA_UNICA, QuestionType.MULTIPLA})


class AnamnesisRuleError(ValueError):
    pass


# ---------- estrutura do formulário ----------


def check_question(q: dict[str, Any]) -> None:
    """Coerência entre tipo, opções e alerta de uma pergunta já tipada."""
    qtype = QuestionType(q["type"])
    options = q.get("options")
    alert_options = q.get("alert_options")
    label = f'Pergunta "{q["id"]}"'
    if qtype in CHOICE_TYPES:
        if not options or len(options) < 2:
            raise AnamnesisRuleError(f"{label}: informe ao menos duas opções.")
        if len(options) > MAX_OPTIONS:
            raise AnamnesisRuleError(f"{label}: no máximo {MAX_OPTIONS} opções.")
        if len({o.casefold() for o in options}) != len(options):
            raise AnamnesisRuleError(f"{label}: há opções repetidas.")
    elif options is not None:
        raise AnamnesisRuleError(f"{label}: só perguntas de escolha têm opções.")
    if alert_options is not None:
        if qtype not in CHOICE_TYPES:
            raise AnamnesisRuleError(f"{label}: opções de alerta só valem para escolhas.")
        if not q.get("alert"):
            raise AnamnesisRuleError(f"{label}: marque a pergunta como alerta.")
        if not alert_options or not set(alert_options) <= set(options or []):
            raise AnamnesisRuleError(f"{label}: as opções de alerta precisam estar nas opções.")


def check_questions(questions: list[dict[str, Any]]) -> None:
    if len(questions) > MAX_QUESTIONS:
        raise AnamnesisRuleError(f"No máximo {MAX_QUESTIONS} perguntas.")
    ids = [q["id"] for q in questions]
    if len(set(ids)) != len(ids):
        raise AnamnesisRuleError("Há perguntas com o mesmo identificador.")


# ---------- respostas ----------


def _invalid(q: dict[str, Any], why: str) -> AnamnesisRuleError:
    return AnamnesisRuleError(f'Resposta inválida para "{q["text"]}": {why}.')


def _normalize(q: dict[str, Any], value: Any) -> Any:
    """Valor normalizado, ou None quando a pergunta ficou sem resposta."""
    if value is None:
        return None
    qtype = QuestionType(q["type"])
    if qtype is QuestionType.TEXTO:
        if not isinstance(value, str):
            raise _invalid(q, "esperado texto")
        value = value.strip()
        if len(value) > MAX_TEXT_ANSWER:
            raise _invalid(q, f"no máximo {MAX_TEXT_ANSWER} caracteres")
        return value or None
    if qtype is QuestionType.SIM_NAO:
        if not isinstance(value, bool):
            raise _invalid(q, "esperado sim ou não")
        return value
    if qtype is QuestionType.ESCOLHA_UNICA:
        if not isinstance(value, str) or value not in q["options"]:
            raise _invalid(q, "opção inexistente")
        return value
    if qtype is QuestionType.MULTIPLA:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise _invalid(q, "esperada uma lista de opções")
        if any(v not in q["options"] for v in value):
            raise _invalid(q, "opção inexistente")
        chosen = set(value)
        ordered = [o for o in q["options"] if o in chosen]  # ordem do formulário, sem repetir
        return ordered or None
    if qtype is QuestionType.NUMERO:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _invalid(q, "esperado um número")
        if not math.isfinite(value) or abs(value) > MAX_NUMBER:
            raise _invalid(q, "número fora do intervalo")
        return value
    # DATA
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise _invalid(q, "esperada uma data AAAA-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise _invalid(q, "data inexistente") from None


def validate_answers(questions: list[dict[str, Any]], answers: dict[str, Any]) -> dict[str, Any]:
    """Confere as respostas contra as perguntas da versão e devolve só as preenchidas."""
    by_id = {q["id"]: q for q in questions}
    unknown = sorted(set(answers) - set(by_id))
    if unknown:
        raise AnamnesisRuleError(
            f"Pergunta(s) inexistente(s) neste formulário: {', '.join(unknown)}."
        )
    result: dict[str, Any] = {}
    for q in questions:
        value = _normalize(q, answers.get(q["id"]))
        if value is None:
            if q.get("required"):
                raise AnamnesisRuleError(f'Responda a pergunta obrigatória "{q["text"]}".')
            continue
        result[q["id"]] = value
    return result


def compute_alerts(
    questions: list[dict[str, Any]], answers: dict[str, Any]
) -> list[dict[str, Any]]:
    """Respostas que viram alerta, na ordem do formulário (ver docstring do módulo)."""
    alerts = []
    for q in questions:
        if not q.get("alert") or q["id"] not in answers:
            continue
        value = answers[q["id"]]
        qtype = QuestionType(q["type"])
        alert_options = q.get("alert_options")
        if qtype is QuestionType.SIM_NAO:
            if value is not True:
                continue
        elif qtype is QuestionType.ESCOLHA_UNICA and alert_options:
            if value not in alert_options:
                continue
        elif qtype is QuestionType.MULTIPLA and alert_options:
            value = [v for v in value if v in alert_options]
            if not value:
                continue
        alerts.append({"question_id": q["id"], "text": q["text"], "answer": value})
    return alerts
