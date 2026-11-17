"""Estado do odontograma pronto para desenhar, o mesmo para o 2D e o 3D (regras puras).

As duas visões leem os mesmos eventos (`regras.rebuild`) e a mesma legenda; aqui só se
decide a cor de cada face e se o dente aparece:

- Cor da face: a do item mais importante marcado na face; sem marcação na face, a do item
  mais importante marcado no dente inteiro (ex.: coroa pinta as cinco faces); sem nenhum,
  `None` (cor natural do dente).
- Importância: patologia, depois planejado, depois realizado (o que pede ação aparece por
  cima); empate pela ordem da legenda e pelo código.
- Dente oculto: há marcação de dente inteiro com efeito 3D `ocultar` (ex.: ausente). O 2D
  pode mostrá-lo riscado; o 3D não desenha a malha.
- Dente marcado fora da arcada do paciente (ex.: marcação antiga num decíduo que já caiu)
  continua na lista com `in_arch = False`, para nada sumir do histórico.
"""

import uuid
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from app.modules.odontograma import arcada
from app.modules.odontograma.regras import FACES, Key, face_label, is_deciduous

KIND_PRIORITY = {"patologia": 0, "planejado": 1, "realizado": 2}


class StatusLike(Protocol):
    id: uuid.UUID
    code: str
    name: str
    color: str
    kind: Any
    sort_order: int
    display_3d: Any


def _value(v: Any) -> str:
    return getattr(v, "value", v)


def priority(status: StatusLike) -> tuple[int, int, str]:
    return (KIND_PRIORITY[_value(status.kind)], status.sort_order, status.code)


def mark(status: StatusLike) -> dict[str, Any]:
    return {
        "status_id": status.id,
        "code": status.code,
        "name": status.name,
        "color": status.color,
        "kind": _value(status.kind),
    }


def _best_color(statuses: list[StatusLike]) -> str | None:
    return min(statuses, key=priority).color if statuses else None


def build(
    arch_teeth: Iterable[int],
    marks: Iterable[Key],
    statuses: Mapping[uuid.UUID, StatusLike],
) -> list[dict[str, Any]]:
    """Um item por dente da arcada e por dente marcado fora dela, na ordem de leitura."""
    arch = set(arch_teeth)
    whole: dict[int, list[StatusLike]] = {}
    faces: dict[tuple[int, str], list[StatusLike]] = {}
    for tooth, face, status_id in marks:
        status = statuses[status_id]
        if face is None:
            whole.setdefault(tooth, []).append(status)
        else:
            faces.setdefault((tooth, face), []).append(status)

    out = []
    for tooth in arcada.sort_teeth(arch | set(whole) | {t for t, _ in faces}):
        tooth_marks = sorted(whole.get(tooth, []), key=priority)
        whole_color = _best_color(tooth_marks)
        face_out = {}
        for face in FACES:
            face_marks = sorted(faces.get((tooth, face), []), key=priority)
            face_out[face_label(tooth, face)] = {
                "face": face,
                "node": f"{tooth}_{face}",
                "color": _best_color(face_marks) or whole_color,
                "marks": [mark(s) for s in face_marks],
            }
        out.append(
            {
                "tooth": tooth,
                "deciduous": is_deciduous(tooth),
                "in_arch": tooth in arch,
                "hidden": any(_value(s.display_3d) == "ocultar" for s in tooth_marks),
                "node": f"dente_{tooth}",
                "color": whole_color,
                "whole": [mark(s) for s in tooth_marks],
                "faces": face_out,
            }
        )
    return out


def diff(before: set[Key], after: set[Key]) -> tuple[list[Key], list[Key]]:
    """(marcações que entraram, marcações que saíram), na ordem de leitura."""

    def order(key: Key):
        tooth, face, status_id = key
        return (arcada.display_key(tooth), face or "", str(status_id))

    return sorted(after - before, key=order), sorted(before - after, key=order)
