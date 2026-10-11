"""Malha de triângulos reconstruída a partir de um dicionário .bbmodel.

A prévia é gerada a partir do arquivo exportado (e não do modelo interno),
para que as imagens mostrem exatamente o que o Blockbench vai abrir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .geometry import pivot_matrix, transform_points
from .uv import FACE_NORMALS, FACES, rect_bounds, uv_to_local


@dataclass
class BoneInfo:
    name: str
    uuid: str
    parent: Optional[str]
    pivot_rest: np.ndarray
    pivot_world: np.ndarray
    matrix: np.ndarray


@dataclass
class Mesh:
    positions: np.ndarray  # (T, 3, 3)
    uvs: np.ndarray  # (T, 3, 2) em unidades de UV (0..resolução)
    normals: np.ndarray  # (T, 3)
    uv_rects: np.ndarray  # (T, 4) u_min, v_min, u_max, v_max da face
    element_index: np.ndarray  # (T,)
    face_names: list[str]
    element_names: list[str]
    bones: dict[str, BoneInfo] = field(default_factory=dict)
    uv_size: tuple[int, int] = (16, 16)

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        pts = self.positions.reshape(-1, 3)
        return pts.min(axis=0), pts.max(axis=0)


def _adjusted_from_to(el: dict[str, Any]) -> tuple[list[float], list[float]]:
    frm = [float(v) for v in el["from"]]
    to = [float(v) for v in el["to"]]
    inflate = float(el.get("inflate", 0) or 0)
    stretch = el.get("stretch", [1, 1, 1])
    out_f, out_t = [], []
    for i in range(3):
        half = (to[i] - frm[i]) / 2
        center = frm[i] + half
        out_f.append(center - (half + inflate) * float(stretch[i]))
        out_t.append(center + (half + inflate) * float(stretch[i]))
    return out_f, out_t


def build_mesh(bbmodel: dict[str, Any]) -> Mesh:
    groups = {g["uuid"]: g for g in bbmodel.get("groups", [])}
    elements = {e["uuid"]: e for e in bbmodel.get("elements", [])}
    parent_of_element: dict[str, Optional[str]] = {}
    group_parent: dict[str, Optional[str]] = {}

    def walk(nodes: list[Any], parent: Optional[str]) -> None:
        for node in nodes:
            if isinstance(node, str):
                parent_of_element[node] = parent
            else:
                uid = node["uuid"]
                group_parent[uid] = parent
                walk(node.get("children", []), uid)

    walk(bbmodel.get("outliner", []), None)

    group_matrix: dict[str, np.ndarray] = {}

    def gmat(uid: Optional[str]) -> np.ndarray:
        if uid is None:
            return np.eye(4)
        if uid in group_matrix:
            return group_matrix[uid]
        g = groups[uid]
        m = gmat(group_parent.get(uid)) @ pivot_matrix(g.get("origin", [0, 0, 0]), g.get("rotation", [0, 0, 0]))
        group_matrix[uid] = m
        return m

    bones: dict[str, BoneInfo] = {}
    for uid, g in groups.items():
        if uid not in group_parent:
            continue
        m = gmat(uid)
        parent_uid = group_parent.get(uid)
        pivot = np.array(g.get("origin", [0, 0, 0]), dtype=float)
        parent_m = gmat(parent_uid)
        bones[g["name"]] = BoneInfo(
            name=g["name"],
            uuid=uid,
            parent=groups[parent_uid]["name"] if parent_uid else None,
            pivot_rest=pivot,
            pivot_world=transform_points(parent_m, pivot[None])[0],
            matrix=m,
        )

    positions, uvs, normals, rects, el_index, face_names = [], [], [], [], [], []
    element_names = []
    for idx, (uid, el) in enumerate(elements.items()):
        element_names.append(el.get("name", uid))
        if el.get("type", "cube") != "cube" or el.get("visibility", True) is False:
            continue
        m = gmat(parent_of_element.get(uid)) @ pivot_matrix(el.get("origin", [0, 0, 0]), el.get("rotation", [0, 0, 0]))
        frm, to = _adjusted_from_to(el)
        for face in FACES:
            fd = el.get("faces", {}).get(face)
            if fd is None or fd.get("texture") is None or fd.get("enabled", True) is False:
                continue
            uv = [float(v) for v in fd["uv"]]
            rot = int(fd.get("rotation", 0) or 0)
            corners_uv = np.array([[uv[0], uv[1]], [uv[2], uv[1]], [uv[2], uv[3]], [uv[0], uv[3]]])
            local = uv_to_local(face, uv, frm, to, corners_uv[:, 0], corners_uv[:, 1], rotation=rot)
            world = transform_points(m, local)
            e1 = world[1] - world[0]
            e2 = world[3] - world[0]
            if np.linalg.norm(np.cross(e1, e2)) < 1e-9:
                continue
            n = m[:3, :3] @ np.array(FACE_NORMALS[face])
            rb = rect_bounds(uv)
            for tri in ((0, 1, 2), (0, 2, 3)):
                positions.append(world[list(tri)])
                uvs.append(corners_uv[list(tri)])
                normals.append(n)
                rects.append(rb)
                el_index.append(idx)
                face_names.append(face)
    res = bbmodel.get("resolution", {"width": 16, "height": 16})
    return Mesh(
        positions=np.array(positions, dtype=float).reshape(-1, 3, 3),
        uvs=np.array(uvs, dtype=float).reshape(-1, 3, 2),
        normals=np.array(normals, dtype=float).reshape(-1, 3),
        uv_rects=np.array(rects, dtype=float).reshape(-1, 4),
        element_index=np.array(el_index, dtype=int),
        face_names=face_names,
        element_names=element_names,
        bones=bones,
        uv_size=(int(res["width"]), int(res["height"])),
    )
