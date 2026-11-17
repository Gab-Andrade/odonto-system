"""Interpretador de fórmulas de preço. Funções puras, sem banco.

Uma fórmula é uma lista de passos nomeados, avaliados em ordem; cada passo pode usar as
variáveis de entrada e os passos anteriores. O último passo precisa se chamar `preco`.

    custo_hora    = custos_fixos_mensais / horas_produtivas_mes
    custo_clinico = custo_hora * tempo_horas
    ...
    preco         = custo_total / (1 - (impostos_pct + taxa_cartao_pct + margem_pct) / 100)

Segurança: a expressão é analisada com `ast` e só passa se tiver exclusivamente números,
nomes, + - * /, comparações e as funções da lista branca. Nada é executado com eval().
Todo o cálculo é em Decimal (nunca float), para não haver diferença de centavos.
"""

import ast
import re
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_UP,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Any

CENTS = Decimal("0.01")
MAX_PRICE = Decimal("9999999999.99")
# Limite para qualquer valor intermediário: muito acima de qualquer custo real, mas impede
# que passos encadeados cresçam sem controle (1e999, x*x*x...).
MAX_INTERMEDIATE = Decimal("1e15")
MAX_EXPRESSION_CHARS = 500
MAX_NODES = 200
MAX_STEPS = 30
NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,49}$")
RESULT_STEP = "preco"

# Entradas calculadas pelo sistema para cada procedimento (a partir da ficha técnica).
SYSTEM_INPUTS = {
    "custo_materiais": "soma de quantidade × custo unitário dos materiais da ficha técnica",
    "tempo_minutos": "tempo do procedimento na ficha técnica",
    "tempo_horas": "tempo do procedimento em horas (tempo_minutos / 60)",
}

FUNCTIONS = {
    "min": "menor valor: min(a, b, ...)",
    "max": "maior valor: max(a, b, ...)",
    "arredondar": "arredondar(valor, casas) — meio para cima",
    "se": "se(condição, valor_se_verdadeiro, valor_se_falso)",
}

RESERVED_NAMES = set(SYSTEM_INPUTS) | set(FUNCTIONS) | {RESULT_STEP}

# Fórmula padrão: "preço por dentro" — impostos, taxa e margem incidem sobre o preço.
DEFAULT_FORMULA: list[dict[str, str]] = [
    {"nome": "custo_hora", "expressao": "custos_fixos_mensais / horas_produtivas_mes"},
    {"nome": "custo_clinico", "expressao": "custo_hora * tempo_horas"},
    {"nome": "pro_labore", "expressao": "pro_labore_hora * tempo_horas"},
    {"nome": "custo_total", "expressao": "custo_materiais + custo_clinico + pro_labore"},
    {
        "nome": "preco",
        "expressao": "custo_total / (1 - (impostos_pct + taxa_cartao_pct + margem_pct) / 100)",
    },
]

# Variáveis que a fórmula padrão espera que a clínica cadastre.
DEFAULT_VARIABLES = {
    "custos_fixos_mensais": "aluguel, salários, contas etc. por mês (R$)",
    "horas_produtivas_mes": "horas de atendimento por mês",
    "pro_labore_hora": "remuneração do dentista por hora (R$)",
    "impostos_pct": "impostos sobre o faturamento (%)",
    "taxa_cartao_pct": "taxa média de cartão (%)",
    "margem_pct": "margem de lucro desejada (%)",
}


class FormulaError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ---------- Análise ----------

_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_UNARY_OPS = (ast.UAdd, ast.USub)
_CMP_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)


def parse_expression(expression: str) -> ast.Expression:
    if not expression or not expression.strip():
        raise FormulaError("Expressão vazia.")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise FormulaError(f"Expressão com mais de {MAX_EXPRESSION_CHARS} caracteres.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        raise FormulaError(f"Expressão inválida: '{expression}'.") from None

    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise FormulaError("Expressão complexa demais.")
    source = expression.strip()
    for node in nodes:
        _check_node(node)
        if isinstance(node, ast.Constant):
            node.decimal_value = _literal(source, node)  # type: ignore[attr-defined]
    return tree


def _literal(source: str, node: ast.Constant) -> Decimal:
    """Valor exato do número como foi escrito (um float perderia dígitos)."""
    text = ast.get_source_segment(source, node) or repr(node.value)
    try:
        value = Decimal(text.replace("_", ""))
    except InvalidOperation:
        raise FormulaError(f"Número inválido: '{text}'.") from None
    if not value.is_finite() or abs(value) > MAX_INTERMEDIATE:
        raise FormulaError(f"Número fora do limite permitido: '{text}'.")
    return value


def _check_node(node: ast.AST) -> None:
    if isinstance(node, ast.Expression | ast.Load):
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise FormulaError("Só números são aceitos como valores fixos.")
        return
    if isinstance(node, ast.Name):
        if not NAME_RE.match(node.id):
            raise FormulaError(f"Nome inválido: '{node.id}'.")
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BIN_OPS):
            raise FormulaError("Operador não permitido. Use + - * /.")
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _UNARY_OPS):
            raise FormulaError("Operador não permitido.")
        return
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or not isinstance(node.ops[0], _CMP_OPS):
            raise FormulaError("Comparação não permitida. Use uma comparação por vez.")
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            allowed = ", ".join(FUNCTIONS)
            raise FormulaError(f"Função não permitida. Disponíveis: {allowed}.")
        if node.keywords:
            raise FormulaError("Funções não aceitam argumentos nomeados.")
        return
    if isinstance(node, _BIN_OPS + _UNARY_OPS + _CMP_OPS):
        return  # os próprios operadores aparecem como nós no ast.walk
    raise FormulaError("Elemento não permitido na expressão.")


def names_used(tree: ast.Expression) -> set[str]:
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called


@dataclass
class CompiledFormula:
    steps: list[dict[str, str]]
    trees: list[ast.Expression]
    inputs: set[str]  # nomes que precisam vir de fora (variáveis e entradas do sistema)


def compile_formula(steps: list[dict[str, Any]]) -> CompiledFormula:
    """Valida a estrutura: nomes, ordem e expressões. Não precisa dos valores."""
    if not steps:
        raise FormulaError("A fórmula precisa de pelo menos um passo.")
    if len(steps) > MAX_STEPS:
        raise FormulaError(f"A fórmula pode ter no máximo {MAX_STEPS} passos.")

    clean: list[dict[str, str]] = []
    trees: list[ast.Expression] = []
    defined: set[str] = set()
    inputs: set[str] = set()
    for i, step in enumerate(steps, start=1):
        name = str(step.get("nome", "")).strip()
        expression = str(step.get("expressao", "")).strip()
        if not NAME_RE.match(name):
            raise FormulaError(
                f"Passo {i}: nome '{name}' inválido. Use letras minúsculas, números e _."
            )
        if name in defined:
            raise FormulaError(f"Passo {i}: '{name}' já foi definido antes.")
        if name in RESERVED_NAMES and name != RESULT_STEP:
            raise FormulaError(f"Passo {i}: '{name}' é um nome reservado do sistema.")
        try:
            tree = parse_expression(expression)
        except FormulaError as exc:
            raise FormulaError(f"Passo {i} ({name}): {exc.message}") from None
        if name in names_used(tree):
            raise FormulaError(f"Passo {i}: '{name}' não pode usar a si mesmo.")
        inputs |= names_used(tree) - defined
        defined.add(name)
        clean.append({"nome": name, "expressao": expression})
        trees.append(tree)

    if clean[-1]["nome"] != RESULT_STEP:
        raise FormulaError(f"O último passo precisa se chamar '{RESULT_STEP}'.")
    if any(s["nome"] == RESULT_STEP for s in clean[:-1]):
        raise FormulaError(f"'{RESULT_STEP}' só pode ser o último passo.")
    return CompiledFormula(steps=clean, trees=trees, inputs=inputs)


# ---------- Avaliação ----------


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(repr(value))  # float literal da expressão: '0.1' → Decimal('0.1')


def _eval(node: ast.AST, env: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        return getattr(node, "decimal_value", None) or _to_decimal(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise FormulaError(f"Variável '{node.id}' não definida.")
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, env)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise FormulaError("Divisão por zero.")
        return left / right
    if isinstance(node, ast.Compare):
        left, right = _eval(node.left, env), _eval(node.comparators[0], env)
        op = node.ops[0]
        result = {
            ast.Lt: left < right,
            ast.LtE: left <= right,
            ast.Gt: left > right,
            ast.GtE: left >= right,
            ast.Eq: left == right,
            ast.NotEq: left != right,
        }[type(op)]
        return Decimal(1) if result else Decimal(0)
    if isinstance(node, ast.Call):
        return _call(node, env)
    raise FormulaError("Elemento não permitido na expressão.")  # inalcançável após a análise


def _call(node: ast.Call, env: dict[str, Decimal]) -> Decimal:
    name = node.func.id  # type: ignore[attr-defined]
    if name == "se":
        if len(node.args) != 3:
            raise FormulaError("se() precisa de 3 argumentos: condição, se verdadeiro, se falso.")
        condition = _eval(node.args[0], env)
        return _eval(node.args[1] if condition != 0 else node.args[2], env)
    args = [_eval(a, env) for a in node.args]
    if name in ("min", "max"):
        if not args:
            raise FormulaError(f"{name}() precisa de pelo menos um valor.")
        return min(args) if name == "min" else max(args)
    if name == "arredondar":
        if len(args) != 2 or args[1] != args[1].to_integral_value() or not 0 <= args[1] <= 6:
            raise FormulaError("arredondar() precisa de (valor, casas), com casas de 0 a 6.")
        return args[0].quantize(Decimal(1).scaleb(-int(args[1])), rounding=ROUND_HALF_UP)
    raise FormulaError(f"Função '{name}' não permitida.")


@dataclass
class FormulaResult:
    price: Decimal
    steps: list[dict[str, str]]  # {"nome", "expressao", "valor"}


def run_formula(compiled: CompiledFormula, inputs: dict[str, Decimal]) -> FormulaResult:
    missing = sorted(compiled.inputs - set(inputs))
    if missing:
        raise FormulaError(f"Variáveis sem valor: {', '.join(missing)}.")

    env = dict(inputs)
    trace: list[dict[str, str]] = []
    for name, value in inputs.items():
        if not value.is_finite() or abs(value) > MAX_INTERMEDIATE:
            raise FormulaError(f"O valor de '{name}' está fora do limite permitido.")
    with localcontext() as ctx:
        ctx.prec = 34
        for signal in (DivisionByZero, InvalidOperation, Overflow):
            ctx.traps[signal] = True
        for step, tree in zip(compiled.steps, compiled.trees, strict=True):
            try:
                value = _eval(tree, env)
                if not value.is_finite() or abs(value) > MAX_INTERMEDIATE:
                    raise FormulaError("resultado fora do limite permitido.")
                shown = display_value(value)
            except FormulaError as exc:
                raise FormulaError(f"{step['nome']}: {exc.message}") from None
            except DecimalException:
                raise FormulaError(f"{step['nome']}: cálculo inválido.") from None
            env[step["nome"]] = value
            trace.append({"nome": step["nome"], "expressao": step["expressao"], "valor": shown})

    price = env[RESULT_STEP].quantize(CENTS, rounding=ROUND_HALF_UP)
    if price < 0:
        raise FormulaError(
            "O preço deu negativo. Confira se impostos + taxa + margem passam de 100%."
        )
    if price > MAX_PRICE:
        raise FormulaError("O preço calculado passa do limite permitido.")
    return FormulaResult(price=price, steps=trace)


def display_value(value: Decimal) -> str:
    """Valor legível na memória de cálculo: até 4 casas, sem zeros à direita."""
    shown = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize()
    return format(shown, "f")
