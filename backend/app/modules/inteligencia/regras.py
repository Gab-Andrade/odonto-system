"""Catálogo de regras de alerta e validação dos parâmetros (puro, testável sem banco).

Cada regra tem parâmetros padrão; a clínica pode desligá-la ou mudar os parâmetros
(`alert_rule_settings`). Os alertas são calculados na hora a partir dos dados existentes:
não há envio externo (WhatsApp/e-mail ficam em stand-by).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.core.roles import Role

ALL_ROLES = frozenset(Role)
CLINICAL_ROLES = frozenset({Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB})
FINANCE_ROLES = frozenset({Role.ADMIN, Role.GESTOR, Role.RECEPCAO})
MANAGER_CLINICIAN_ROLES = frozenset({Role.ADMIN, Role.GESTOR, Role.DENTISTA})

SEVERITIES = ("alta", "media", "baixa")
SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}

MAX_SNOOZE_DAYS = 365
DEFAULT_SNOOZE_DAYS = 30
MAX_TERMS = 10
MAX_TERM_LENGTH = 40


class RuleConfigError(ValueError):
    pass


@dataclass(frozen=True)
class IntParam:
    name: str
    label: str
    default: int
    minimum: int
    maximum: int


@dataclass(frozen=True)
class TermsParam:
    """Lista de trechos procurados na descrição ou no código do procedimento."""

    name: str
    label: str
    default: tuple[str, ...]


Param = IntParam | TermsParam


@dataclass(frozen=True)
class RuleDef:
    code: str
    title: str
    description: str
    category: str  # clinico, orcamento, agenda, financeiro
    severity: str
    roles: frozenset[Role]
    params: tuple[Param, ...]

    def defaults(self) -> dict[str, Any]:
        return {
            p.name: list(p.default) if isinstance(p, TermsParam) else p.default for p in self.params
        }


RULES: tuple[RuleDef, ...] = (
    RuleDef(
        code="profilaxia_atrasada",
        title="Profilaxia atrasada",
        description=(
            "Pacientes ativos cuja última profilaxia realizada (item do plano cujo código ou "
            "descrição contém um dos termos) foi há mais de N meses e sem consulta futura. "
            "Quem nunca fez profilaxia registrada no sistema não entra."
        ),
        category="clinico",
        severity="media",
        roles=ALL_ROLES,
        params=(
            IntParam("meses", "Meses desde a última profilaxia", 6, 1, 36),
            TermsParam("termos", "Termos do procedimento", ("profilaxia", "limpeza")),
        ),
    ),
    RuleDef(
        code="canal_sem_retorno",
        title="Tratamento de canal sem retorno",
        description=(
            "Tratamento de canal realizado (item do plano marcado como 'Tratamento de canal' "
            "no odontograma, ou cujo código ou descrição contém um dos termos) há mais de N "
            "dias, sem atendimento depois dele e sem consulta futura."
        ),
        category="clinico",
        severity="alta",
        roles=CLINICAL_ROLES,
        params=(
            IntParam("dias", "Dias sem retorno", 30, 1, 365),
            TermsParam("termos", "Termos do procedimento", ("canal", "endodont")),
        ),
    ),
    RuleDef(
        code="orcamento_aprovado_sem_agendamento",
        title="Orçamento aprovado sem agendamento",
        description=(
            "Orçamento aprovado há mais de N dias, com procedimentos ainda por fazer e sem "
            "consulta futura do paciente."
        ),
        category="orcamento",
        severity="media",
        roles=ALL_ROLES,
        params=(IntParam("dias", "Dias desde a aprovação", 7, 0, 365),),
    ),
    RuleDef(
        code="orcamento_sem_resposta",
        title="Orçamento sem resposta",
        description=(
            "Orçamento emitido há mais de N dias, ainda dentro da validade, sem a decisão do "
            "paciente."
        ),
        category="orcamento",
        severity="baixa",
        roles=ALL_ROLES,
        params=(IntParam("dias", "Dias desde a emissão", 7, 1, 365),),
    ),
    RuleDef(
        code="atendimento_aberto",
        title="Atendimento aberto há muito tempo",
        description="Atendimento iniciado há mais de N dias e ainda não fechado.",
        category="clinico",
        severity="media",
        roles=MANAGER_CLINICIAN_ROLES,
        params=(IntParam("dias", "Dias em aberto", 1, 1, 90),),
    ),
    RuleDef(
        code="faltas_repetidas",
        title="Faltas repetidas",
        description="Pacientes com N faltas ou mais nos últimos D dias.",
        category="agenda",
        severity="baixa",
        roles=ALL_ROLES,
        params=(
            IntParam("faltas", "Número de faltas", 2, 1, 20),
            IntParam("dias", "Janela (dias)", 180, 7, 730),
        ),
    ),
    RuleDef(
        code="conta_em_atraso",
        title="Conta a receber em atraso",
        description="Pacientes com parcelas vencidas há mais de N dias e saldo em aberto.",
        category="financeiro",
        severity="media",
        roles=FINANCE_ROLES,
        params=(IntParam("dias", "Dias de atraso", 1, 0, 365),),
    ),
)

BY_CODE: dict[str, RuleDef] = {r.code: r for r in RULES}
CODES = tuple(BY_CODE)


def get_rule(code: str) -> RuleDef:
    try:
        return BY_CODE[code]
    except KeyError:
        raise RuleConfigError("Regra de alerta inexistente.") from None


def visible_rules(role: Role) -> list[RuleDef]:
    return [r for r in RULES if role in r.roles]


def _clean_terms(param: TermsParam, value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RuleConfigError(f'"{param.label}": informe ao menos um termo.')
    if len(value) > MAX_TERMS:
        raise RuleConfigError(f'"{param.label}": no máximo {MAX_TERMS} termos.')
    terms: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuleConfigError(f'"{param.label}": os termos são textos.')
        term = " ".join(item.split()).lower()
        if not term or len(term) > MAX_TERM_LENGTH:
            raise RuleConfigError(
                f'"{param.label}": cada termo com 1 a {MAX_TERM_LENGTH} caracteres.'
            )
        if term not in terms:
            terms.append(term)
    return terms


def validate_params(rule: RuleDef, given: dict[str, Any] | None) -> dict[str, Any]:
    """Parâmetros completos: os informados (validados) sobre os padrões da regra."""
    given = dict(given or {})
    known = {p.name for p in rule.params}
    unknown = sorted(set(given) - known)
    if unknown:
        raise RuleConfigError("Parâmetro desconhecido: " + ", ".join(unknown) + ".")
    result = rule.defaults()
    for p in rule.params:
        if p.name not in given:
            continue
        value = given[p.name]
        if isinstance(p, IntParam):
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuleConfigError(f'"{p.label}" precisa ser um número inteiro.')
            if not p.minimum <= value <= p.maximum:
                raise RuleConfigError(f'"{p.label}" deve ficar entre {p.minimum} e {p.maximum}.')
            result[p.name] = value
        else:
            result[p.name] = _clean_terms(p, value)
    return result


def effective_params(rule: RuleDef, stored: dict[str, Any] | None) -> dict[str, Any]:
    """Parâmetros guardados sobre os padrões; um valor guardado que não vale mais (regra
    mudou de faixa) volta ao padrão em vez de quebrar a listagem."""
    result = rule.defaults()
    for name, value in (stored or {}).items():
        try:
            result.update({name: validate_params(rule, {name: value})[name]})
        except RuleConfigError:
            continue
    return result


def months_before(day: date, months: int) -> date:
    """Mesmo dia N meses antes (fim do mês quando o dia não existe)."""
    total = day.year * 12 + day.month - 1 - months
    year, month = divmod(total, 12)
    month += 1
    for d in (day.day, 30, 29, 28):
        try:
            return date(year, month, d)
        except ValueError:
            continue
    raise AssertionError("inalcançável")


def check_snooze(until: date | None, today: date) -> date:
    if until is None:
        return today + timedelta(days=DEFAULT_SNOOZE_DAYS)
    if until <= today:
        raise RuleConfigError("A data para voltar a mostrar precisa ser no futuro.")
    if until > today + timedelta(days=MAX_SNOOZE_DAYS):
        raise RuleConfigError(f"Dispense por no máximo {MAX_SNOOZE_DAYS} dias.")
    return until


def matches_terms(code: str | None, description: str | None, terms: list[str]) -> bool:
    text = f"{code or ''} {description or ''}".lower()
    return any(t in text for t in terms)
