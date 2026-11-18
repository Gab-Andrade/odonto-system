from datetime import date, timedelta

import pytest

from app.core.roles import Role
from app.modules.inteligencia import regras


def test_catalog_codes_are_unique_and_have_defaults():
    assert len(regras.CODES) == len(set(regras.CODES))
    for rule in regras.RULES:
        assert rule.severity in regras.SEVERITIES
        assert regras.validate_params(rule, {}) == rule.defaults()


def test_validate_params_merges_and_checks_ranges():
    rule = regras.get_rule("profilaxia_atrasada")
    assert regras.validate_params(rule, {"meses": 12})["meses"] == 12
    with pytest.raises(regras.RuleConfigError, match="entre"):
        regras.validate_params(rule, {"meses": 0})
    with pytest.raises(regras.RuleConfigError, match="inteiro"):
        regras.validate_params(rule, {"meses": True})
    with pytest.raises(regras.RuleConfigError, match="desconhecido"):
        regras.validate_params(rule, {"xpto": 1})


def test_terms_are_normalized_and_deduplicated():
    rule = regras.get_rule("profilaxia_atrasada")
    params = regras.validate_params(rule, {"termos": ["  Profilaxia ", "profilaxia", "LIMPEZA"]})
    assert params["termos"] == ["profilaxia", "limpeza"]
    with pytest.raises(regras.RuleConfigError):
        regras.validate_params(rule, {"termos": []})
    with pytest.raises(regras.RuleConfigError):
        regras.validate_params(rule, {"termos": [1]})


def test_effective_params_ignores_invalid_stored_values():
    rule = regras.get_rule("faltas_repetidas")
    assert regras.effective_params(rule, {"faltas": 999, "dias": 30}) == {"faltas": 2, "dias": 30}


def test_unknown_rule():
    with pytest.raises(regras.RuleConfigError):
        regras.get_rule("nao_existe")


def test_visibility_by_role():
    reception = {r.code for r in regras.visible_rules(Role.RECEPCAO)}
    assert "canal_sem_retorno" not in reception
    assert "conta_em_atraso" in reception
    asb = {r.code for r in regras.visible_rules(Role.ASB)}
    assert "conta_em_atraso" not in asb
    assert "canal_sem_retorno" in asb
    assert len(regras.visible_rules(Role.ADMIN)) == len(regras.RULES)


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2026, 11, 18), 6, date(2026, 5, 18)),
        (date(2026, 3, 31), 1, date(2026, 2, 28)),
        (date(2026, 1, 15), 13, date(2024, 12, 15)),
    ],
)
def test_months_before(day, months, expected):
    assert regras.months_before(day, months) == expected


def test_snooze_limits():
    today = date(2026, 11, 18)
    assert regras.check_snooze(None, today) == today + timedelta(days=30)
    with pytest.raises(regras.RuleConfigError):
        regras.check_snooze(today, today)
    with pytest.raises(regras.RuleConfigError):
        regras.check_snooze(today + timedelta(days=400), today)


def test_matches_terms():
    assert regras.matches_terms("P-01", "Profilaxia adulto", ["profilaxia"])
    assert not regras.matches_terms("REST", "Restauração", ["profilaxia"])
