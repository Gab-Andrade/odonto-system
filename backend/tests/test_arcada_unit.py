"""Arcada do paciente: presets, validação da composição, ordem de leitura e sugestão pela
idade (sem banco)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.odontograma import arcada
from app.modules.odontograma.schemas import ArchIn


def test_presets():
    assert len(arcada.preset("permanente", arcada.THIRD_MOLARS)) == 32
    assert len(arcada.preset("permanente")) == 28
    assert 18 not in arcada.preset("permanente", [28]) and 28 in arcada.preset("permanente", [28])
    assert len(arcada.preset("decidua")) == 20
    mixed = arcada.preset("mista")
    assert len(mixed) == 24 and 16 in mixed and 55 in mixed and 53 in mixed and 13 not in mixed
    with pytest.raises(arcada.ArchRuleError):
        arcada.preset("decidua", [18])
    with pytest.raises(arcada.ArchRuleError):
        arcada.preset("permanente", [17])


def test_display_order():
    order = arcada.preset("permanente", arcada.THIRD_MOLARS)
    assert order[:8] == [18, 17, 16, 15, 14, 13, 12, 11]
    assert order[8:16] == [21, 22, 23, 24, 25, 26, 27, 28]
    assert order[16:24] == [48, 47, 46, 45, 44, 43, 42, 41]
    assert order[24:] == [31, 32, 33, 34, 35, 36, 37, 38]
    assert arcada.preset("decidua")[:5] == [55, 54, 53, 52, 51]
    assert arcada.sort_teeth([11, 16, 55, 21, 65]) == [16, 55, 11, 21, 65]


@pytest.mark.parametrize(
    ("dentition", "teeth", "message"),
    [
        ("permanente", [], "ao menos um"),
        ("permanente", [11, 11], "repetido"),
        ("permanente", [19], "FDI"),
        ("permanente", [11, 51], "decíduos"),
        ("decidua", [51, 11], "permanentes"),
        ("mista", [11, 21], "decíduos e permanentes"),
        ("mista", [11, 51], "mesma posição"),
        ("mista", [36, 75, 35], "mesma posição"),
        ("outra", [11], "Dentição inválida"),
    ],
)
def test_validation_errors(dentition, teeth, message):
    with pytest.raises(arcada.ArchRuleError, match=message):
        arcada.validate(dentition, teeth)


def test_validation_ok_and_slots():
    assert arcada.validate("mista", [36, 75, 46, 85, 11]) == [11, 46, 85, 75, 36]
    assert arcada.slot(55) == (1, 5) and arcada.slot(15) == (1, 5) and arcada.slot(83) == (4, 3)
    assert arcada.is_upper(65) and not arcada.is_upper(75)


def test_default_by_age():
    today = date(2026, 11, 17)
    assert arcada.default_for(None, today)[0] == "permanente"
    assert len(arcada.default_for(None, today)[1]) == 32
    assert arcada.default_for(date(2022, 1, 1), today)[0] == "decidua"
    assert arcada.default_for(date(2018, 1, 1), today)[0] == "mista"
    teen = arcada.default_for(date(2012, 1, 1), today)
    assert teen[0] == "permanente" and len(teen[1]) == 28
    assert len(arcada.default_for(date(1990, 1, 1), today)[1]) == 32
    # Aniversário ainda não chegou no ano: 5 anos, não 6.
    assert arcada.age_on(date(2020, 11, 18), today) == 5
    assert arcada.default_for(date(2020, 11, 18), today)[0] == "decidua"


def test_schema():
    assert ArchIn(dentition="mista", teeth=[11, 51]).teeth == [11, 51]
    with pytest.raises(ValidationError):
        ArchIn(dentition="permanente", third_molars=[17])
    with pytest.raises(ValidationError):
        ArchIn(dentition="permanente", teeth=[19])
    with pytest.raises(ValidationError):
        ArchIn(dentition="adulta")
