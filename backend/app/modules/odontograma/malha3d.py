"""Biblioteca 3D genérica de dentes, gerada por código (sem arquivos binários no repositório).

Cada dente FDI vira um nó `dente_<fdi>` com um filho por face — `<fdi>_M`, `<fdi>_D`,
`<fdi>_O`, `<fdi>_V`, `<fdi>_L` — e um `<fdi>_raiz` (colo e raízes). Assim o frontend pinta
cada face com a cor da legenda, igual ao 2D, e o toque numa malha devolve dente e face (os
`extras` de cada nó trazem `fdi`, `face` e o rótulo clínico: I nos anteriores, P na arcada
superior).

Convenções (milímetros, sistema do glTF, Y para cima):
- Dente isolado: colo em y=0, coroa para +Y (ponta/oclusal), raiz para −Y, face vestibular
  para +Z. A mesial fica em +X ou −X (`mesial_x` nos extras): o lado é escolhido para que
  o posicionamento na arcada seja uma rotação pura, sem espelhamento.
- Arcada: vista de frente do paciente (ele olha para +Z); o lado esquerdo do paciente é +X;
  plano oclusal em y=0, arcada superior acima. Quadrantes 1 e 4 (direita do paciente) ficam
  em x<0.

As formas são simplificadas (caixa arredondada com afinamento incisal, cúspides e raízes
cônicas), suficientes para comunicação com o paciente. Para trocar por modelos feitos no
Blender, mantenha os mesmos nomes de nós e a mesma orientação.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

from app.modules.odontograma import arcada, glb
from app.modules.odontograma.regras import FACES, face_label, is_deciduous, is_valid_tooth

VERSION = "procedural-1"
GENERATOR = f"odonto-system {VERSION}"
GRID = 8  # subdivisões por lado da coroa

Vec3 = tuple[float, float, float]

# Materiais: um por face (o frontend troca a cor) e um para a raiz.
MATERIALS = [glb.Material(f"face_{f}", (0.93, 0.91, 0.84, 1.0), roughness=0.35) for f in FACES]
MATERIALS.append(glb.Material("raiz", (0.86, 0.79, 0.66, 1.0), roughness=0.6))
ROOT_MATERIAL = len(FACES)


@dataclass(frozen=True)
class ToothShape:
    kind: str  # incisivo | canino | pre_molar | molar
    width: float  # mésio-distal
    depth: float  # vestíbulo-lingual
    crown: float  # altura da coroa
    root: float  # comprimento da raiz
    roots: int


def _kind(position: int, deciduous: bool) -> str:
    if position <= 2:
        return "incisivo"
    if position == 3:
        return "canino"
    if deciduous or position >= 6:
        return "molar"
    return "pre_molar"


# (largura, profundidade, coroa, raiz, nº de raízes) por posição, em mm (valores médios).
_PERMANENT_UPPER = {
    1: (8.5, 7.0, 10.5, 13.0, 1), 2: (6.5, 6.0, 9.0, 13.0, 1), 3: (7.5, 8.0, 10.0, 17.0, 1),
    4: (7.0, 9.0, 8.5, 14.0, 2), 5: (6.5, 9.0, 8.0, 14.0, 1), 6: (10.0, 11.0, 7.5, 12.5, 3),
    7: (9.0, 11.0, 7.0, 12.0, 3), 8: (8.5, 10.0, 6.5, 11.0, 3),
}  # fmt: skip
_PERMANENT_LOWER = {
    1: (5.0, 6.0, 9.0, 12.5, 1), 2: (5.5, 6.0, 9.5, 14.0, 1), 3: (7.0, 7.5, 11.0, 16.0, 1),
    4: (7.0, 7.5, 8.5, 14.0, 1), 5: (7.0, 8.0, 8.0, 14.5, 1), 6: (11.0, 10.5, 7.5, 14.0, 2),
    7: (10.5, 10.0, 7.0, 13.0, 2), 8: (10.0, 9.5, 7.0, 11.0, 2),
}  # fmt: skip
_DECIDUOUS_UPPER = {
    1: (6.5, 5.0, 6.0, 10.0, 1), 2: (5.1, 4.8, 5.6, 11.0, 1), 3: (7.0, 7.0, 6.5, 13.0, 1),
    4: (7.3, 8.5, 5.1, 10.0, 3), 5: (8.2, 10.0, 5.7, 11.0, 3),
}  # fmt: skip
_DECIDUOUS_LOWER = {
    1: (4.2, 4.0, 5.0, 9.0, 1), 2: (4.1, 4.2, 5.2, 10.0, 1), 3: (5.0, 5.5, 6.0, 11.5, 1),
    4: (7.7, 7.0, 5.5, 10.0, 2), 5: (9.9, 8.7, 5.5, 11.0, 2),
}  # fmt: skip


def shape(tooth: int) -> ToothShape:
    if not is_valid_tooth(tooth):
        raise ValueError(f"dente FDI inválido: {tooth}")
    position = tooth % 10
    deciduous = is_deciduous(tooth)
    upper = arcada.is_upper(tooth)
    table = (
        (_DECIDUOUS_UPPER if upper else _DECIDUOUS_LOWER)
        if deciduous
        else (_PERMANENT_UPPER if upper else _PERMANENT_LOWER)
    )
    return ToothShape(_kind(position, deciduous), *table[position])


# ---------- geometria ----------


def _smoothstep(lo: float, hi: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


def _cusp(s: float) -> float:
    """0 no centro (sulco) e na borda, 1 em ±0.5 (ponta de cúspide)."""
    return (1 - math.cos(2 * math.pi * s)) / 2


# Lados do cubo: (normal, eixo A, eixo B) com A × B = normal (triângulos para fora).
_SIDES: dict[str, tuple[Vec3, Vec3, Vec3]] = {
    "O": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    "base": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "M": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "D": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "V": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "L": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
}


def _crown_point(s: ToothShape, p: Vec3) -> Vec3:
    """Ponto do cubo [-1, 1]³ → superfície da coroa (mesial em +X)."""
    m = 4.0
    norm = (abs(p[0]) ** m + abs(p[1]) ** m + abs(p[2]) ** m) ** (1 / m)
    u, v, w = (c / norm for c in p)  # caixa arredondada
    t = (v + 1) / 2  # 0 no colo, 1 na oclusal/incisal
    sx = sz = 0.78 + 0.22 * _smoothstep(0.0, 0.45, t)  # constrição cervical
    y = t * s.crown
    if s.kind == "incisivo":
        sz *= 1 - 0.7 * t**1.5
        sx *= 1 + 0.08 * t
    elif s.kind == "canino":
        sz *= 1 - 0.45 * t**1.5
        sx *= 1 - 0.55 * t**2
        y += 0.12 * s.crown * (1 - abs(u)) * _smoothstep(0.7, 1.0, t)
    elif s.kind == "pre_molar":
        y += 0.12 * s.crown * _cusp(w) * (1 - u * u) * _smoothstep(0.75, 1.0, t)
    else:
        y += 0.1 * s.crown * _cusp(u) * _cusp(w) * _smoothstep(0.75, 1.0, t)
    return (u * sx * s.width / 2, y, w * sz * s.depth / 2)


def _grid(s: ToothShape, side: str) -> tuple[list[Vec3], list[int]]:
    normal, a, b = _SIDES[side]
    n = GRID
    points: list[Vec3] = []
    for i in range(n + 1):
        for j in range(n + 1):
            si, rj = -1 + 2 * i / n, -1 + 2 * j / n
            cube = tuple(normal[k] + a[k] * si + b[k] * rj for k in range(3))
            points.append(_crown_point(s, cube))
    indices: list[int] = []
    for i in range(n):
        for j in range(n):
            v00, v10 = i * (n + 1) + j, (i + 1) * (n + 1) + j
            v01, v11 = v00 + 1, v10 + 1
            indices += [v00, v10, v11, v00, v11, v01]
    return points, indices


def _root(s: ToothShape, cx: float, cz: float, scale: float) -> tuple[list[Vec3], list[int]]:
    """Raiz cônica com seção elíptica, do interior da coroa (y=0.4) até o ápice."""
    segments, rings = 12, 8
    rx, rz = 0.36 * s.width * scale, 0.36 * s.depth * scale
    top = 0.4
    points: list[Vec3] = []
    for r in range(rings):
        f = r / rings
        radius = 1 - f**1.8
        y = top - f * (s.root + top)
        for k in range(segments):
            ang = 2 * math.pi * k / segments
            points.append((cx + rx * radius * math.cos(ang), y, cz + rz * radius * math.sin(ang)))
    apex = len(points)
    points.append((cx, -s.root, cz))
    indices: list[int] = []
    for r in range(rings - 1):
        for k in range(segments):
            a0 = r * segments + k
            a1 = r * segments + (k + 1) % segments
            b0, b1 = a0 + segments, a1 + segments
            indices += [a0, a1, b1, a0, b1, b0]
    last = (rings - 1) * segments
    for k in range(segments):
        indices += [last + k, last + (k + 1) % segments, apex]
    return points, indices


def _root_layout(s: ToothShape) -> list[tuple[float, float, float]]:
    """(centro x, centro z, escala) de cada raiz."""
    w, d = s.width, s.depth
    if s.roots == 3:
        return [(0.22 * w, 0.18 * d, 0.45), (-0.22 * w, 0.18 * d, 0.45), (0, -0.22 * d, 0.5)]
    if s.roots == 2 and s.kind == "pre_molar":
        return [(0, 0.2 * d, 0.55), (0, -0.2 * d, 0.55)]
    if s.roots == 2:
        return [(0.25 * w, 0, 0.5), (-0.25 * w, 0, 0.5)]
    return [(0, 0, 1.0)]


def _normals(points: list[Vec3], indices: list[int], acc: dict) -> None:
    """Acumula normais de triângulo por posição (soldando vértices repetidos nas bordas)."""
    for i in range(0, len(indices), 3):
        p0, p1, p2 = (points[k] for k in indices[i : i + 3])
        e1 = tuple(p1[k] - p0[k] for k in range(3))
        e2 = tuple(p2[k] - p0[k] for k in range(3))
        n = (
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0],
        )
        for p in (p0, p1, p2):
            key = tuple(round(c, 5) for c in p)
            old = acc.get(key, (0.0, 0.0, 0.0))
            acc[key] = (old[0] + n[0], old[1] + n[1], old[2] + n[2])


def _unit(v: Vec3) -> Vec3:
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _mesh(points, indices, acc, material: int, mirror: bool) -> glb.Mesh:
    normals = [_unit(acc[tuple(round(c, 5) for c in p)]) for p in points]
    if mirror:  # mesial para −X: espelha em X e inverte o sentido dos triângulos
        points = [(-p[0], p[1], p[2]) for p in points]
        normals = [(-n[0], n[1], n[2]) for n in normals]
        indices = [indices[i + k] for i in range(0, len(indices), 3) for k in (0, 2, 1)]
    return glb.Mesh(points, normals, indices, material)


# ---------- posicionamento na arcada ----------

# Curvas (parábolas z = frente − k·x²) e larguras das vagas (mm), da linha média para trás.
_ARCH = {
    # (frente, k, altura do plano oclusal)
    "superior": (0.0, 0.055, 0.5),
    "inferior": (-2.0, 0.06, -0.5),
    "superior_decidua": (0.0, 0.07, 0.5),
    "inferior_decidua": (-1.5, 0.075, -0.5),
}
_CONTACT = 0.1  # folga entre dentes


def _slot_widths(upper: bool, deciduous_arch: bool) -> dict[int, float]:
    if deciduous_arch:
        table = _DECIDUOUS_UPPER if upper else _DECIDUOUS_LOWER
    else:
        table = _PERMANENT_UPPER if upper else _PERMANENT_LOWER
    return {p: row[0] for p, row in table.items()}


def _walk(front: float, k: float, length: float) -> tuple[float, float, float, float]:
    """Ponto (x≥0) a `length` mm da linha média sobre a parábola, e a direção da curva."""
    x, travelled, step = 0.0, 0.0, 0.01
    while travelled < length:
        travelled += step * math.sqrt(1 + (2 * k * x) ** 2)
        x += step
    dx, dz = _unit((1.0, -2 * k * x, 0.0))[:2]
    return x, front - k * x * x, dx, dz


@dataclass(frozen=True)
class Placement:
    translation: Vec3
    rotation: tuple[float, float, float, float]  # quatérnio x, y, z, w
    mesial_x: int  # +1: mesial em +X no dente isolado; −1: em −X


def _quaternion(cols: tuple[Vec3, Vec3, Vec3]) -> tuple[float, float, float, float]:
    (m00, m10, m20), (m01, m11, m21), (m02, m12, m22) = cols
    trace = m00 + m11 + m22
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1)
        q = ((m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, 0.25 / s)
    elif m00 > m11 and m00 > m22:
        s = 2 * math.sqrt(1 + m00 - m11 - m22)
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = 2 * math.sqrt(1 + m11 - m00 - m22)
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = 2 * math.sqrt(1 + m22 - m00 - m11)
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    if q[3] < 0:
        q = (-q[0], -q[1], -q[2], -q[3])
    return q


def _det(a: Vec3, b: Vec3, c: Vec3) -> float:
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


@lru_cache(maxsize=256)
def placement(tooth: int, deciduous_arch: bool = False) -> Placement:
    """Posição do dente na arcada. `deciduous_arch`: arcada só de decíduos (menor);
    na mista, os decíduos ocupam a vaga do sucessor permanente."""
    s = shape(tooth)
    upper = arcada.is_upper(tooth)
    quadrant, position = arcada.slot(tooth)
    deciduous_arch = deciduous_arch and is_deciduous(tooth)
    curve = ("superior" if upper else "inferior") + ("_decidua" if deciduous_arch else "")
    front, k, plane = _ARCH[curve]
    widths = _slot_widths(upper, deciduous_arch)
    center = sum(widths[p] + _CONTACT for p in range(1, position)) + widths[position] / 2
    x, z, dx, dz = _walk(front, k, center)
    left = quadrant in (2, 3)  # lado esquerdo do paciente: +X
    sign = 1 if left else -1
    mesial: Vec3 = (-dx * sign, 0.0, -dz)
    vestibular: Vec3 = (-dz * sign, 0.0, dx)
    occlusal: Vec3 = (0.0, -1.0, 0.0) if upper else (0.0, 1.0, 0.0)
    mesial_x = 1 if _det(mesial, occlusal, vestibular) > 0 else -1
    x_axis = tuple(c * mesial_x for c in mesial)
    y = plane + s.crown if upper else plane - s.crown
    return Placement((x * sign, y, z), _quaternion((x_axis, occlusal, vestibular)), mesial_x)


# ---------- montagem dos nós e arquivos ----------


def _tooth_node(tooth: int, place: Placement | None = None) -> glb.Node:
    s = shape(tooth)
    mirror = placement(tooth).mesial_x < 0
    acc: dict = {}
    parts: dict[str, tuple[list[Vec3], list[int]]] = {}
    for side in _SIDES:
        parts[side] = _grid(s, side)
        _normals(*parts[side], acc)
    roots = [_root(s, cx, cz, sc) for cx, cz, sc in _root_layout(s)]
    for pts, idx in roots:
        _normals(pts, idx, acc)

    children = [
        glb.Node(
            name=f"{tooth}_{face}",
            mesh=_mesh(*parts[face], acc, FACES.index(face), mirror),
            extras={"fdi": tooth, "face": face, "rotulo": face_label(tooth, face)},
        )
        for face in FACES
    ]
    # Colo (base da coroa) e raízes numa malha só.
    points, indices = list(parts["base"][0]), list(parts["base"][1])
    for pts, idx in roots:
        offset = len(points)
        points += pts
        indices += [i + offset for i in idx]
    children.append(
        glb.Node(
            name=f"{tooth}_raiz",
            mesh=_mesh(points, indices, acc, ROOT_MATERIAL, mirror),
            extras={"fdi": tooth, "face": None},
        )
    )
    return glb.Node(
        name=f"dente_{tooth}",
        children=children,
        translation=place.translation if place else None,
        rotation=place.rotation if place else None,
        extras={
            "fdi": tooth,
            "deciduo": is_deciduous(tooth),
            "tipo": s.kind,
            "mesial_x": placement(tooth).mesial_x,
        },
    )


@lru_cache(maxsize=64)
def tooth_glb(tooth: int) -> bytes:
    """Um dente isolado, no sistema local (colo na origem)."""
    return glb.build([_tooth_node(tooth)], MATERIALS, generator=GENERATOR)


def is_deciduous_arch(teeth: tuple[int, ...]) -> bool:
    return all(is_deciduous(t) for t in teeth)


@lru_cache(maxsize=16)
def arch_glb(teeth: tuple[int, ...]) -> bytes:
    """Arcada montada com os dentes informados (validados antes)."""
    deciduous_arch = is_deciduous_arch(teeth)
    nodes = [_tooth_node(t, placement(t, deciduous_arch)) for t in teeth]
    root = glb.Node(name="arcada", children=nodes, extras={"dentes": list(teeth)})
    return glb.build([root], MATERIALS, generator=GENERATOR)


def library() -> list[dict]:
    """Manifesto: cada dente com tipo e posição na arcada permanente/mista e na decídua."""
    out = []
    for tooth in arcada.sort_teeth(arcada.ALL_PERMANENT + arcada.ALL_DECIDUOUS):
        s = shape(tooth)
        entry = {
            "fdi": tooth,
            "deciduous": is_deciduous(tooth),
            "kind": s.kind,
            "nodes": [f"{tooth}_{f}" for f in FACES] + [f"{tooth}_raiz"],
            "face_labels": {f: face_label(tooth, f) for f in FACES},
            "placement": _placement_dict(placement(tooth)),
        }
        if is_deciduous(tooth):
            entry["placement_deciduous_arch"] = _placement_dict(placement(tooth, True))
        out.append(entry)
    return out


def placement_dict(tooth: int, deciduous_arch: bool = False) -> dict:
    return _placement_dict(placement(tooth, deciduous_arch))


def _placement_dict(p: Placement) -> dict:
    return {
        "translation": [round(c, 4) + 0.0 for c in p.translation],
        "rotation": [round(c, 6) + 0.0 for c in p.rotation],
        "mesial_x": p.mesial_x,
    }


CONVENTIONS = {
    "eixos": "glTF (Y para cima), em milímetros.",
    "dente_isolado": (
        "Colo em y=0, coroa para +Y, raiz para -Y, vestibular para +Z; mesial em +X ou -X "
        "conforme mesial_x."
    ),
    "arcada": (
        "Paciente de frente, olhando para +Z; esquerda do paciente em +X (quadrantes 2 e 3); "
        "plano oclusal em y=0, arcada superior acima."
    ),
    "nos": "dente_<fdi> com filhos <fdi>_M, _D, _O, _V, _L (faces) e <fdi>_raiz.",
    "faces": "Gravadas como M, D, O, V, L; o rótulo clínico (I, P) está em face_labels.",
}
