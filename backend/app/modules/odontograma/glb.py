"""Gravador mínimo de glTF 2.0 binário (.glb), sem dependências.

Só o necessário para a biblioteca de dentes: nós com nome, translação, rotação e `extras`;
malhas de triângulos com POSITION, NORMAL e índices; materiais PBR de cor sólida. A saída é
determinística (mesma entrada, mesmos bytes), o que permite ETag e cache.
"""

import json
import struct
from dataclasses import dataclass, field
from typing import Any

Vec3 = tuple[float, float, float]

_FLOAT = 5126
_UINT16 = 5123
_UINT32 = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_TRIANGLES = 4


@dataclass
class Mesh:
    positions: list[Vec3]
    normals: list[Vec3]
    indices: list[int]
    material: int


@dataclass
class Node:
    name: str
    mesh: Mesh | None = None
    children: list["Node"] = field(default_factory=list)
    translation: Vec3 | None = None
    rotation: tuple[float, float, float, float] | None = None  # quatérnio x, y, z, w
    extras: dict[str, Any] | None = None


@dataclass(frozen=True)
class Material:
    name: str
    color: tuple[float, float, float, float]
    roughness: float = 0.5
    metallic: float = 0.0


def _pad(data: bytearray, multiple: int = 4, byte: bytes = b"\x00") -> None:
    while len(data) % multiple:
        data += byte


def _round(v: float) -> float:
    # Arredonda para evitar diferenças de ponto flutuante entre plataformas no ETag.
    return round(v, 6) + 0.0


def build(roots: list[Node], materials: list[Material], *, generator: str) -> bytes:
    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": generator},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "meshes": [],
        "materials": [
            {
                "name": m.name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [_round(c) for c in m.color],
                    "metallicFactor": m.metallic,
                    "roughnessFactor": m.roughness,
                },
            }
            for m in materials
        ],
        "accessors": [],
        "bufferViews": [],
        "buffers": [],
    }
    blob = bytearray()

    def view(data: bytes, target: int) -> int:
        _pad(blob)
        gltf["bufferViews"].append(
            {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target}
        )
        blob.extend(data)
        return len(gltf["bufferViews"]) - 1

    def accessor(view_index: int, component: int, count: int, kind: str, **extra) -> int:
        gltf["accessors"].append(
            {"bufferView": view_index, "componentType": component, "count": count, "type": kind}
            | extra
        )
        return len(gltf["accessors"]) - 1

    def add_mesh(name: str, mesh: Mesh) -> int:
        if not mesh.positions or not mesh.indices or len(mesh.indices) % 3:
            raise ValueError(f"malha inválida: {name}")
        fmt3 = f"<{3 * len(mesh.positions)}f"
        packed_pos = struct.pack(fmt3, *(c for p in mesh.positions for c in p))
        # min/max exatos dos float32 gravados (o glTF exige que batam com o buffer).
        flat = struct.unpack(fmt3, packed_pos)
        lo = [min(flat[i::3]) for i in range(3)]
        hi = [max(flat[i::3]) for i in range(3)]
        pos = accessor(
            view(packed_pos, _ARRAY_BUFFER),
            _FLOAT, len(mesh.positions), "VEC3", min=lo, max=hi,
        )  # fmt: skip
        nflat = [_round(c) for n in mesh.normals for c in n]
        nor = accessor(
            view(struct.pack(f"<{len(nflat)}f", *nflat), _ARRAY_BUFFER),
            _FLOAT, len(mesh.normals), "VEC3",
        )  # fmt: skip
        wide = len(mesh.positions) > 65535
        fmt, comp = ("I", _UINT32) if wide else ("H", _UINT16)
        packed = struct.pack(f"<{len(mesh.indices)}{fmt}", *mesh.indices)
        idx = accessor(view(packed, _ELEMENT_ARRAY_BUFFER), comp, len(mesh.indices), "SCALAR")
        gltf["meshes"].append(
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {"POSITION": pos, "NORMAL": nor},
                        "indices": idx,
                        "material": mesh.material,
                        "mode": _TRIANGLES,
                    }
                ],
            }
        )
        return len(gltf["meshes"]) - 1

    def add_node(node: Node) -> int:
        out: dict[str, Any] = {"name": node.name}
        if node.translation is not None:
            out["translation"] = [_round(c) for c in node.translation]
        if node.rotation is not None:
            out["rotation"] = [_round(c) for c in node.rotation]
        if node.extras:
            out["extras"] = node.extras
        if node.mesh is not None:
            out["mesh"] = add_mesh(node.name, node.mesh)
        gltf["nodes"].append(out)
        index = len(gltf["nodes"]) - 1
        if node.children:
            out["children"] = [add_node(c) for c in node.children]
        return index

    gltf["scenes"][0]["nodes"] = [add_node(r) for r in roots]
    _pad(blob)
    gltf["buffers"].append({"byteLength": len(blob)})

    header = bytearray(json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode())
    _pad(header, byte=b" ")
    total = 12 + 8 + len(header) + 8 + len(blob)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total),
            struct.pack("<I4s", len(header), b"JSON"),
            bytes(header),
            struct.pack("<I4s", len(blob), b"BIN\x00"),
            bytes(blob),
        )
    )


def read_json(data: bytes) -> dict[str, Any]:
    """Lê o JSON de um .glb (usado em testes e na conferência de arquivos externos)."""
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total != len(data):
        raise ValueError("não é um glTF 2.0 binário")
    length, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON":
        raise ValueError("primeiro bloco do .glb não é JSON")
    return json.loads(data[20 : 20 + length])
