"""Composição da arcada do paciente (regras puras, testáveis sem banco).

A arcada diz quais dentes o modelo do paciente tem (decídua, mista ou permanente, com 0 a 4
terceiros molares). É a base do odontograma 3D e da grade do 2D. Não confundir com a
marcação "ausente" da legenda: a arcada descreve a dentição (o que existe ou deveria
existir na idade), a marcação registra um dente perdido.

Cada posição da arcada ("vaga") é ocupada por um dente só: o decíduo 5x/6x/7x/8x de posição
1–5 ocupa a mesma vaga do permanente 1x/2x/3x/4x de mesma posição (o sucessor). As posições
6–8 só existem na dentição permanente.
"""

from collections.abc import Iterable
from datetime import date

from app.modules.odontograma.regras import is_deciduous, is_valid_tooth

PERMANENTE = "permanente"
DECIDUA = "decidua"
MISTA = "mista"
DENTITIONS = (PERMANENTE, DECIDUA, MISTA)

THIRD_MOLARS = (18, 28, 38, 48)
MAX_TEETH = 52

ALL_PERMANENT = tuple(q * 10 + p for q in (1, 2, 3, 4) for p in range(1, 9))
ALL_DECIDUOUS = tuple(q * 10 + p for q in (5, 6, 7, 8) for p in range(1, 6))
# Mista típica (~6 a 9 anos): incisivos e primeiros molares permanentes; caninos e molares
# decíduos.
TYPICAL_MIXED = tuple(q * 10 + p for q in (1, 2, 3, 4) for p in (1, 2, 6)) + tuple(
    q * 10 + p for q in (5, 6, 7, 8) for p in (3, 4, 5)
)


class ArchRuleError(ValueError):
    pass


def is_upper(tooth: int) -> bool:
    return tooth // 10 in (1, 2, 5, 6)


def slot(tooth: int) -> tuple[int, int]:
    """Vaga do dente: (quadrante permanente 1–4, posição 1–8)."""
    quadrant, position = divmod(tooth, 10)
    return (quadrant - 4 if quadrant >= 5 else quadrant, position)


def display_key(tooth: int) -> tuple[int, int, int]:
    """Ordem de leitura do odontograma: 18→11, 21→28, 48→41, 31→38 (decíduos na vaga do
    sucessor, depois dele)."""
    quadrant, position = slot(tooth)
    arch = 0 if quadrant in (1, 2) else 1
    # Da esquerda para a direita de quem olha o paciente: quadrantes 1 e 4 primeiro, do
    # fundo para a frente; 2 e 3 depois, da frente para o fundo.
    order = -position if quadrant in (1, 4) else 10 + position
    return (arch, order, 1 if is_deciduous(tooth) else 0)


def sort_teeth(teeth: Iterable[int]) -> list[int]:
    return sorted(teeth, key=display_key)


def preset(dentition: str, third_molars: Iterable[int] | None = None) -> list[int]:
    """Composição padrão de uma dentição. Os sisos só valem na permanente."""
    molars = set(third_molars or ())
    if not molars <= set(THIRD_MOLARS):
        raise ArchRuleError("Terceiros molares válidos: 18, 28, 38 e 48.")
    if dentition == PERMANENTE:
        teeth = [t for t in ALL_PERMANENT if t % 10 != 8 or t in molars]
    elif molars:
        raise ArchRuleError("Terceiros molares só na dentição permanente.")
    elif dentition == DECIDUA:
        teeth = list(ALL_DECIDUOUS)
    elif dentition == MISTA:
        teeth = list(TYPICAL_MIXED)
    else:
        raise ArchRuleError("Dentição inválida: use permanente, decidua ou mista.")
    return sort_teeth(teeth)


def validate(dentition: str, teeth: Iterable[int]) -> list[int]:
    """Valida uma composição explícita e a devolve na ordem de leitura."""
    teeth = list(teeth)
    if dentition not in DENTITIONS:
        raise ArchRuleError("Dentição inválida: use permanente, decidua ou mista.")
    if not teeth:
        raise ArchRuleError("A arcada precisa ter ao menos um dente.")
    if len(teeth) > MAX_TEETH:
        raise ArchRuleError(f"No máximo {MAX_TEETH} dentes.")
    invalid = [t for t in teeth if not is_valid_tooth(t)]
    if invalid:
        raise ArchRuleError(f"Dente inválido na numeração FDI: {invalid[0]}.")
    if len(set(teeth)) != len(teeth):
        raise ArchRuleError("Dente repetido na arcada.")
    deciduous = [t for t in teeth if is_deciduous(t)]
    permanent = [t for t in teeth if not is_deciduous(t)]
    if dentition == PERMANENTE and deciduous:
        raise ArchRuleError("Dentição permanente não tem dentes decíduos; use mista.")
    if dentition == DECIDUA and permanent:
        raise ArchRuleError("Dentição decídua não tem dentes permanentes; use mista.")
    if dentition == MISTA and not (deciduous and permanent):
        raise ArchRuleError("Dentição mista precisa de dentes decíduos e permanentes.")
    taken: dict[tuple[int, int], int] = {}
    for tooth in teeth:
        other = taken.setdefault(slot(tooth), tooth)
        if other != tooth:
            raise ArchRuleError(f"Os dentes {other} e {tooth} ocupam a mesma posição na arcada.")
    return sort_teeth(teeth)


def age_on(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def default_for(birth: date | None, today: date) -> tuple[str, list[int]]:
    """Arcada sugerida enquanto nada foi registrado para o paciente, pela idade.

    Sem data de nascimento ou adulto: permanente com os 4 sisos (32 dentes, a grade
    habitual do odontograma). Até 5 anos: decídua; 6 a 11: mista típica; 12 a 17:
    permanente sem sisos.
    """
    if birth is None:
        return PERMANENTE, preset(PERMANENTE, THIRD_MOLARS)
    age = age_on(birth, today)
    if age < 6:
        return DECIDUA, preset(DECIDUA)
    if age < 12:
        return MISTA, preset(MISTA)
    if age < 18:
        return PERMANENTE, preset(PERMANENTE)
    return PERMANENTE, preset(PERMANENTE, THIRD_MOLARS)
