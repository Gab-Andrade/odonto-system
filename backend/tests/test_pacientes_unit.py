from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.pacientes import dados
from app.modules.pacientes.schemas import PatientCreate


@pytest.mark.parametrize("cpf", ["52998224725", "11144477735", "12345678909"])
def test_valid_cpf(cpf):
    assert dados.is_valid_cpf(cpf)


@pytest.mark.parametrize("cpf", ["52998224724", "11111111111", "1234567890", "abcdefghijk", ""])
def test_invalid_cpf(cpf):
    assert not dados.is_valid_cpf(cpf)


def test_normalize_cpf_and_phone():
    assert dados.normalize_cpf("529.982.247-25") == "52998224725"
    assert dados.normalize_phone("(11) 98765-4321") == "11987654321"
    with pytest.raises(ValueError, match="CPF"):
        dados.normalize_cpf("529.982.247-24")
    with pytest.raises(ValueError, match="Telefone"):
        dados.normalize_phone("123")


def test_search_name_ignores_accents_case_and_spaces():
    assert dados.search_name("  José  da CONCEIÇÃO ", "Zé") == "jose da conceicao ze"
    assert dados.search_name("Ana", None) == "ana"


def test_mask_cpf():
    assert dados.mask_cpf("52998224725") == "***.982.247-**"
    assert dados.mask_cpf(None) is None


def test_age_and_minor():
    assert dados.age_on(date(2010, 6, 15), date(2028, 6, 14)) == 17
    assert dados.age_on(date(2010, 6, 15), date(2028, 6, 15)) == 18
    assert dados.is_minor(date(2010, 6, 15), date(2028, 6, 14))
    assert not dados.is_minor(None, date(2028, 6, 14))


def test_escape_like():
    assert dados.escape_like("50%_a\\b") == "50\\%\\_a\\\\b"


def test_schema_normalizes_and_validates():
    p = PatientCreate(
        full_name=" Ana Souza ",
        phone="(11) 3333-4444",
        cpf="529.982.247-25",
        zip_code="01310-100",
        state="sp",
    )
    assert (p.full_name, p.phone, p.cpf, p.zip_code, p.state) == (
        "Ana Souza",
        "1133334444",
        "52998224725",
        "01310100",
        "SP",
    )
    with pytest.raises(ValidationError):
        PatientCreate(full_name="Ana", phone="11999999999", cpf="000.000.000-00")
    with pytest.raises(ValidationError):
        PatientCreate(full_name="Ana", phone="11999999999", birth_date=date(2999, 1, 1))
