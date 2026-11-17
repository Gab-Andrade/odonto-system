"""Regras puras do odontograma (testáveis sem banco)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

# Faces gravadas. Na entrada, I (incisal) vira O e P (palatina) vira L.
FACES = ("M", "D", "O", "V", "L")
FACE_ALIASES = {"I": "O", "P": "L"}


class OdontogramRuleError(ValueError):
    pass


def is_valid_tooth(tooth: int) -> bool:
    """FDI: permanentes 11–18, 21–28, 31–38, 41–48; decíduos 51–55 … 81–85."""
    quadrant, position = divmod(tooth, 10)
    if 1 <= quadrant <= 4:
        return 1 <= position <= 8
    if 5 <= quadrant <= 8:
        return 1 <= position <= 5
    return False


def is_deciduous(tooth: int) -> bool:
    return tooth // 10 >= 5


def normalize_face(face: str | None) -> str | None:
    if face is None:
        return None
    code = face.strip().upper()
    code = FACE_ALIASES.get(code, code)
    if code not in FACES:
        raise OdontogramRuleError("Face inválida: use M, D, O/I, V ou L/P.")
    return code


def face_label(tooth: int, face: str) -> str:
    """Rótulo clínico da face: incisal nos anteriores, palatina na arcada superior."""
    quadrant, position = divmod(tooth, 10)
    anterior = position <= 3
    upper = quadrant in (1, 2, 5, 6)
    if face == "O" and anterior:
        return "I"
    if face == "L" and upper:
        return "P"
    return face


Key = tuple[int, str | None, uuid.UUID]  # (dente, face, item da legenda)


@dataclass(frozen=True)
class Event:
    tooth: int
    face: str | None
    status_id: uuid.UUID
    action: str  # "marcar" | "remover"


def rebuild(events: Iterable[Event]) -> set[Key]:
    """Marcações vigentes depois de aplicar os eventos, em ordem."""
    marks: set[Key] = set()
    for e in events:
        key = (e.tooth, e.face, e.status_id)
        if e.action == "marcar":
            marks.add(key)
        else:
            marks.discard(key)
    return marks


def check_batch(current: set[Key], changes: list[Event]) -> None:
    """Valida um lote contra o estado atual: sem repetir dente/face/item no lote, não
    marcar o que já está marcado, não remover o que não está."""
    seen: set[Key] = set()
    for e in changes:
        key = (e.tooth, e.face, e.status_id)
        where = f"dente {e.tooth}" + (f", face {face_label(e.tooth, e.face)}" if e.face else "")
        if key in seen:
            raise OdontogramRuleError(f"Item repetido no mesmo envio ({where}).")
        seen.add(key)
        if e.action == "marcar" and key in current:
            raise OdontogramRuleError(f"Já está marcado ({where}).")
        if e.action == "remover" and key not in current:
            raise OdontogramRuleError(f"Não há essa marcação para remover ({where}).")


# Legenda padrão criada para cada clínica (código, nome, cor, tipo, escopo).
# Cores: vermelho = patologia, laranja = planejado, azul = realizado.
DEFAULT_LEGEND: tuple[tuple[str, str, str, str, str], ...] = (
    ("carie", "Cárie", "#D32F2F", "patologia", "face"),
    ("fratura", "Fratura", "#C62828", "patologia", "dente"),
    ("ausente", "Ausente", "#616161", "patologia", "dente"),
    ("restauracao_planejada", "Restauração a fazer", "#F57C00", "planejado", "face"),
    ("endodontia_planejada", "Tratamento de canal a fazer", "#F57C00", "planejado", "dente"),
    ("extracao_indicada", "Extração indicada", "#EF6C00", "planejado", "dente"),
    ("restauracao", "Restauração", "#1565C0", "realizado", "face"),
    ("selante", "Selante", "#1E88E5", "realizado", "face"),
    ("endodontia", "Tratamento de canal", "#1565C0", "realizado", "dente"),
    ("coroa", "Coroa", "#0D47A1", "realizado", "dente"),
    ("implante", "Implante", "#283593", "realizado", "dente"),
)
