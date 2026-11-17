"""Interpretador de fórmulas de preço (sem banco)."""

from decimal import Decimal

import pytest

from app.modules.precificacao import formulas as f

D = Decimal

INPUTS = {
    "custos_fixos_mensais": D("20000"),
    "horas_produtivas_mes": D("160"),
    "pro_labore_hora": D("100"),
    "impostos_pct": D("6"),
    "taxa_cartao_pct": D("4"),
    "margem_pct": D("20"),
    "custo_materiais": D("35.50"),
    "tempo_minutos": D("60"),
    "tempo_horas": D("1"),
}


def test_default_formula_price_by_inside():
    # custo_hora 125; clínico 125; pró-labore 100; total 260,50; 260,50 / 0,70 = 372,142857...
    result = f.run_formula(f.compile_formula(f.DEFAULT_FORMULA), INPUTS)
    assert result.price == D("372.14")
    values = {s["nome"]: s["valor"] for s in result.steps}
    assert values == {
        "custo_hora": "125",
        "custo_clinico": "125",
        "pro_labore": "100",
        "custo_total": "260.5",
        "preco": "372.1429",
    }


def test_compile_reports_inputs_needed():
    compiled = f.compile_formula(f.DEFAULT_FORMULA)
    assert compiled.inputs == set(f.DEFAULT_VARIABLES) | {"custo_materiais", "tempo_horas"}


def test_missing_variables_listed():
    inputs = {k: v for k, v in INPUTS.items() if k not in ("margem_pct", "impostos_pct")}
    with pytest.raises(f.FormulaError, match="sem valor: impostos_pct, margem_pct"):
        f.run_formula(f.compile_formula(f.DEFAULT_FORMULA), inputs)


def test_negative_price_when_percentages_exceed_100():
    inputs = {**INPUTS, "margem_pct": D("95")}
    with pytest.raises(f.FormulaError, match="passam de 100%"):
        f.run_formula(f.compile_formula(f.DEFAULT_FORMULA), inputs)


def test_division_by_zero():
    inputs = {**INPUTS, "horas_produtivas_mes": D("0")}
    with pytest.raises(f.FormulaError, match="custo_hora: Divisão por zero"):
        f.run_formula(f.compile_formula(f.DEFAULT_FORMULA), inputs)


def test_functions_and_decimal_precision():
    steps = [
        {"nome": "base", "expressao": "0.1 + 0.2"},  # em float daria 0.30000000000000004
        {"nome": "minimo", "expressao": "max(base * 100, 50)"},
        {"nome": "preco", "expressao": "se(minimo > 40, arredondar(minimo / 3, 2), 0)"},
    ]
    result = f.run_formula(f.compile_formula(steps), {})
    assert [s["valor"] for s in result.steps] == ["0.3", "50", "16.67"]
    assert result.price == D("16.67")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('x')",
        "open('/etc/passwd')",
        "custo.__class__",
        "[1, 2]",
        "'texto'",
        "2 ** 1000",
        "lambda: 1",
        "a if b else c",
        "custo_materiais and 1",
        "1 < 2 < 3",
        "max(a=1)",
        "True",
        "x[0]",
    ],
)
def test_rejects_anything_outside_the_whitelist(expression):
    with pytest.raises(f.FormulaError):
        f.compile_formula([{"nome": "preco", "expressao": expression}])


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([], "pelo menos um passo"),
        ([{"nome": "custo", "expressao": "1"}], "último passo precisa se chamar 'preco'"),
        ([{"nome": "Preço", "expressao": "1"}], "inválido"),
        ([{"nome": "a", "expressao": "1"}, {"nome": "a", "expressao": "2"}], "já foi definido"),
        ([{"nome": "tempo_horas", "expressao": "1"}], "reservado"),
        ([{"nome": "preco", "expressao": "preco + 1"}], "a si mesmo"),
        (
            [{"nome": "preco", "expressao": "1"}, {"nome": "preco", "expressao": "2"}],
            "já foi definido",
        ),
        ([{"nome": "preco", "expressao": ""}], "vazia"),
        ([{"nome": "preco", "expressao": "1 +"}], "inválida"),
        ([{"nome": "preco", "expressao": "1" + " + 1" * 300}], "caracteres|complexa"),
    ],
)
def test_structure_errors(steps, message):
    with pytest.raises(f.FormulaError, match=message):
        f.compile_formula(steps)


def test_step_can_only_use_previous_steps_or_inputs():
    steps = [
        {"nome": "a", "expressao": "b + 1"},  # b vem depois: vira entrada externa
        {"nome": "b", "expressao": "2"},
        {"nome": "preco", "expressao": "a"},
    ]
    compiled = f.compile_formula(steps)
    assert compiled.inputs == {"b"}


def test_arredondar_validation():
    with pytest.raises(f.FormulaError, match="casas de 0 a 6"):
        f.run_formula(f.compile_formula([{"nome": "preco", "expressao": "arredondar(1, 9)"}]), {})


# ---------- limites numéricos (revisão) ----------


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([{"nome": "preco", "expressao": "1e999"}], "fora do limite"),
        ([{"nome": "preco", "expressao": "1e16"}], "fora do limite"),
        (
            [
                {"nome": "a", "expressao": "10000000000"},
                {"nome": "preco", "expressao": "a * a * a"},
            ],
            "preco: resultado fora do limite",
        ),
    ],
)
def test_huge_numbers_are_a_clean_error(steps, message):
    with pytest.raises(f.FormulaError, match=message):
        f.run_formula(f.compile_formula(steps), {})


def test_chained_growth_stops_at_limit():
    steps = [{"nome": "x0", "expressao": "1000"}]
    steps += [{"nome": f"x{i}", "expressao": f"x{i - 1} * x{i - 1}"} for i in range(1, 10)]
    steps.append({"nome": "preco", "expressao": "x9"})
    with pytest.raises(f.FormulaError, match="fora do limite"):
        f.run_formula(f.compile_formula(steps), {})


def test_huge_input_variable_rejected():
    with pytest.raises(f.FormulaError, match="'custo' está fora do limite"):
        f.run_formula(
            f.compile_formula([{"nome": "preco", "expressao": "custo"}]), {"custo": D("1e20")}
        )


def test_literals_keep_all_digits():
    compiled = f.compile_formula([{"nome": "preco", "expressao": "0.123456789012345678901 * 100"}])
    # Em float, os dígitos depois do 17º se perderiam.
    assert f.run_formula(compiled, {}).steps[0]["valor"] == "12.3457"
    exact = f.compile_formula([{"nome": "preco", "expressao": "0.105 * 100 - 10.5"}])
    assert f.run_formula(exact, {}).price == D("0.00")
