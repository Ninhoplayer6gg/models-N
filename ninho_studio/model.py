"""Representação interna do modelo: ossos (grupos), cubos e marcos.

Coordenadas seguem o Blockbench: unidades em pixels (16 = 1 bloco), Y para
cima, chão em Y = 0, a criatura olha para -Z (norte) e o lado direito do
animal fica em +X (leste). Os ``from``/``to`` dos cubos são absolutos na pose
de repouso, como no arquivo .bbmodel; as rotações dos grupos dão a postura.
"""

from __future__ import annotations

import uuid as uuidlib
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import numpy as np

from .geometry import Vec3, pivot_matrix, transform_points

NINHO_UUID_NAMESPACE = uuidlib.UUID("6f1c2a52-8d0e-4b8f-9a43-1c7d5e2b9a10")


@dataclass
class Cube:
    name: str
    frm: Vec3
    to: Vec3
    origin: Vec3
    rotation: Vec3 = (0.0, 0.0, 0.0)
    inflate: float = 0.0
    mirror_uv: bool = False
    uv_offset: tuple[int, int] = (0, 0)
    part: str = ""
    material: str = "skin"  # skin | teeth | claw | spike | crest
    tags: dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 0 = essencial; maior = detalhe opcional
    uuid: str = ""
    bone: str = ""

    @property
    def size(self) -> Vec3:
        return (self.to[0] - self.frm[0], self.to[1] - self.frm[1], self.to[2] - self.frm[2])

    def corners(self) -> np.ndarray:
        x0, y0, z0 = self.frm
        x1, y1, z1 = self.to
        return np.array(
            [[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)],
            dtype=float,
        )


@dataclass
class Bone:
    name: str
    pivot: Vec3
    rotation: Vec3 = (0.0, 0.0, 0.0)
    parent: Optional[str] = None
    cubes: list[Cube] = field(default_factory=list)
    uuid: str = ""
    is_open: bool = False


@dataclass
class Landmark:
    """Ponto de referência para a pintura (ex.: olho) preso a uma face de um cubo."""

    name: str
    bone: str
    cube: str
    face: str
    point: Vec3
    data: dict[str, Any] = field(default_factory=dict)


class Model:
    def __init__(self, name: str, texture_size: int = 128):
        self.name = name
        self.texture_width = texture_size
        self.texture_height = texture_size
        self.bones: dict[str, Bone] = {}
        self.landmarks: dict[str, Landmark] = {}
        self.meta: dict[str, Any] = {}

    # -- construção -------------------------------------------------------
    def add_bone(self, name: str, pivot: Vec3, rotation: Vec3 = (0.0, 0.0, 0.0), parent: Optional[str] = None) -> Bone:
        if name in self.bones:
            raise ValueError(f"osso duplicado: {name}")
        if parent is not None and parent not in self.bones:
            raise ValueError(f"osso pai inexistente: {parent}")
        bone = Bone(name=name, pivot=tuple(float(v) for v in pivot), rotation=tuple(float(v) for v in rotation), parent=parent)
        self.bones[name] = bone
        return bone

    def add_cube(
        self,
        bone: str,
        name: str,
        frm: Vec3,
        size: Vec3,
        part: str,
        material: str = "skin",
        priority: int = 0,
        tags: Optional[dict[str, Any]] = None,
        origin: Optional[Vec3] = None,
    ) -> Cube:
        b = self.bones[bone]
        if any(s < 0 for s in size):
            raise ValueError(f"tamanho negativo em {bone}/{name}: {size}")
        if any(abs(s - round(s)) > 1e-9 for s in size):
            raise ValueError(f"box UV exige tamanhos inteiros: {bone}/{name} {size}")
        existing = {c.name for c in b.cubes}
        final_name = name
        k = 2
        while final_name in existing:
            final_name = f"{name}_{k}"
            k += 1
        frm = tuple(float(v) for v in frm)
        to = tuple(frm[i] + float(size[i]) for i in range(3))
        cube = Cube(
            name=final_name,
            frm=frm,
            to=to,
            origin=tuple(float(v) for v in (origin if origin is not None else b.pivot)),
            part=part,
            material=material,
            priority=priority,
            tags=dict(tags or {}),
            bone=bone,
        )
        b.cubes.append(cube)
        return cube

    def remove_cube(self, cube: Cube) -> None:
        self.bones[cube.bone].cubes.remove(cube)

    def add_landmark(self, lm: Landmark) -> None:
        self.landmarks[lm.name] = lm

    # -- consultas ----------------------------------------------------------
    def children(self, name: Optional[str]) -> list[Bone]:
        return [b for b in self.bones.values() if b.parent == name]

    def roots(self) -> list[Bone]:
        return self.children(None)

    def chain(self, name: str) -> list[Bone]:
        out = []
        cur: Optional[str] = name
        seen = set()
        while cur is not None:
            if cur in seen:
                raise ValueError(f"ciclo na hierarquia em {cur}")
            seen.add(cur)
            bone = self.bones[cur]
            out.append(bone)
            cur = bone.parent
        return list(reversed(out))

    def world_matrix(self, bone_name: str) -> np.ndarray:
        m = np.eye(4)
        for bone in self.chain(bone_name):
            m = m @ pivot_matrix(bone.pivot, bone.rotation)
        return m

    def cube_matrix(self, cube: Cube) -> np.ndarray:
        return self.world_matrix(cube.bone) @ pivot_matrix(cube.origin, cube.rotation)

    def world_pivot(self, bone_name: str) -> np.ndarray:
        bone = self.bones[bone_name]
        return transform_points(self.world_matrix(bone_name), np.array([bone.pivot]))[0]

    def iter_cubes(self) -> Iterator[Cube]:
        for bone in self.bones.values():
            yield from bone.cubes

    @property
    def cube_count(self) -> int:
        return sum(len(b.cubes) for b in self.bones.values())

    def find_cube(self, bone: str, name: str) -> Cube:
        for cube in self.bones[bone].cubes:
            if cube.name == name:
                return cube
        raise KeyError(f"{bone}/{name}")

    def world_corners(self, cube: Cube) -> np.ndarray:
        return transform_points(self.cube_matrix(cube), cube.corners())

    def world_bounds(self, cubes: Optional[list[Cube]] = None) -> tuple[np.ndarray, np.ndarray]:
        pts = np.concatenate([self.world_corners(c) for c in (cubes if cubes is not None else self.iter_cubes())])
        return pts.min(axis=0), pts.max(axis=0)

    # -- edição global -------------------------------------------------------
    def translate(self, dx: float, dy: float, dz: float) -> None:
        d = (dx, dy, dz)
        for bone in self.bones.values():
            bone.pivot = tuple(bone.pivot[i] + d[i] for i in range(3))
            for c in bone.cubes:
                c.frm = tuple(c.frm[i] + d[i] for i in range(3))
                c.to = tuple(c.to[i] + d[i] for i in range(3))
                c.origin = tuple(c.origin[i] + d[i] for i in range(3))
        for lm in self.landmarks.values():
            lm.point = tuple(lm.point[i] + d[i] for i in range(3))

    def assign_uuids(self, seed: int) -> None:
        """UUIDs determinísticos: mesma seed + mesma estrutura = mesmos UUIDs."""
        for bone in self.bones.values():
            bone.uuid = str(uuidlib.uuid5(NINHO_UUID_NAMESPACE, f"{seed}/bone/{bone.name}"))
            for cube in bone.cubes:
                cube.uuid = str(uuidlib.uuid5(NINHO_UUID_NAMESPACE, f"{seed}/cube/{bone.name}/{cube.name}"))
