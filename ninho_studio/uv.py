"""Box UV (igual ao Blockbench) e empacotamento do atlas.

``box_uv_face_rects`` é uma tradução direta de ``Cube.preview_controller.updateUV``
(``js/outliner/types/cube.js`` do Blockbench 5.2.2) e ``uv_to_local`` traduz
``CubeFace.UVToLocal`` do mesmo arquivo. Assim a pintura procedural, a prévia
e o Blockbench concordam sobre qual região da textura cobre cada face.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Hashable, Iterable, Optional, Sequence

import numpy as np

FACES = ("north", "east", "south", "west", "up", "down")
_EPS = 0.0000001


def floored_size(frm: Sequence[float], to: Sequence[float]) -> tuple[int, int, int]:
    """Tamanho usado pelo box UV (``Cube.size(axis, true)``: ``floor(to - from + 1e-7)``)."""
    return tuple(int(math.floor(to[i] - frm[i] + _EPS)) for i in range(3))  # type: ignore[return-value]


def box_uv_footprint(size: Sequence[float]) -> tuple[int, int]:
    """Largura e altura do retângulo ocupado no atlas por um cubo em box UV."""
    w, h, d = (int(math.floor(s + _EPS)) for s in size)
    return 2 * (d + w), d + h


def box_uv_face_rects(
    frm: Sequence[float],
    to: Sequence[float],
    uv_offset: Sequence[float],
    mirror_uv: bool = False,
) -> dict[str, list[float]]:
    """UV de cada face (``[u1, v1, u2, v2]``, como gravado no .bbmodel)."""
    size = floored_size(frm, to)
    face_list = [
        {"face": "east", "from": [0, size[2]], "size": [size[2], size[1]]},
        {"face": "west", "from": [size[2] + size[0], size[2]], "size": [size[2], size[1]]},
        {"face": "up", "from": [size[2] + size[0], size[2]], "size": [-size[0], -size[2]]},
        {"face": "down", "from": [size[2] + size[0] * 2, 0], "size": [-size[0], size[2]]},
        {"face": "south", "from": [size[2] * 2 + size[0], size[2]], "size": [size[0], size[1]]},
        {"face": "north", "from": [size[2], size[2]], "size": [size[0], size[1]]},
    ]
    if mirror_uv:
        for f in face_list:
            f["from"][0] += f["size"][0]
            f["size"][0] *= -1
        east, west = face_list[0], face_list[1]
        east_from, east_size = list(east["from"]), list(east["size"])
        east["from"], east["size"] = list(west["from"]), list(west["size"])
        west["from"], west["size"] = east_from, east_size
    out = {}
    for f in face_list:
        u = f["from"][0] + uv_offset[0]
        v = f["from"][1] + uv_offset[1]
        out[f["face"]] = [u, v, u + f["size"][0], v + f["size"][1]]
    return {face: out[face] for face in FACES}


def _lerp(a: float, b: float, m):
    return a + (b - a) * m


def uv_to_local(
    face: str,
    uv: Sequence[float],
    frm: Sequence[float],
    to: Sequence[float],
    u,
    v,
    rotation: int = 0,
):
    """Ponto 3D (coordenadas absolutas de repouso) correspondente a (u, v) numa face.

    Aceita ``u``/``v`` escalares ou arrays numpy. Equivale a
    ``CubeFace.UVToLocal`` sem subtrair ``origin``.
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    du = uv[2] - uv[0]
    dv = uv[3] - uv[1]
    lx = (u - uv[0]) / du if du != 0 else np.zeros_like(u)
    ly = (v - uv[1]) / dv if dv != 0 else np.zeros_like(v)
    for _ in range(0, int(rotation), 90):
        lx, ly = 1 - ly, lx
    x = np.full_like(lx, frm[0], dtype=float)
    y = np.full_like(lx, frm[1], dtype=float)
    z = np.full_like(lx, frm[2], dtype=float)
    if face == "east":
        x = np.full_like(lx, to[0], dtype=float)
        y = _lerp(to[1], frm[1], ly)
        z = _lerp(to[2], frm[2], lx)
    elif face == "west":
        y = _lerp(to[1], frm[1], ly)
        z = _lerp(frm[2], to[2], lx)
    elif face == "up":
        y = np.full_like(lx, to[1], dtype=float)
        z = _lerp(frm[2], to[2], ly)
        x = _lerp(frm[0], to[0], lx)
    elif face == "down":
        z = _lerp(to[2], frm[2], ly)
        x = _lerp(frm[0], to[0], lx)
    elif face == "south":
        z = np.full_like(lx, to[2], dtype=float)
        y = _lerp(to[1], frm[1], ly)
        x = _lerp(frm[0], to[0], lx)
    elif face == "north":
        y = _lerp(to[1], frm[1], ly)
        x = _lerp(to[0], frm[0], lx)
    else:
        raise ValueError(face)
    return np.stack([x, y, z], axis=-1)


FACE_NORMALS = {
    "north": (0.0, 0.0, -1.0),
    "south": (0.0, 0.0, 1.0),
    "east": (1.0, 0.0, 0.0),
    "west": (-1.0, 0.0, 0.0),
    "up": (0.0, 1.0, 0.0),
    "down": (0.0, -1.0, 0.0),
}


def rect_bounds(uv: Sequence[float]) -> tuple[float, float, float, float]:
    """(u_min, v_min, u_max, v_max) de uma UV possivelmente invertida."""
    return min(uv[0], uv[2]), min(uv[1], uv[3]), max(uv[0], uv[2]), max(uv[1], uv[3])


# ---------------------------------------------------------------------------
# Empacotamento (skyline bottom-left)
# ---------------------------------------------------------------------------


@dataclass
class PackItem:
    key: Hashable
    width: int
    height: int
    group: int = 0


class _Skyline:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.segments: list[list[int]] = [[0, 0, width]]  # [x, y, w]

    def _fit(self, index: int, w: int, h: int) -> Optional[int]:
        x = self.segments[index][0]
        if x + w > self.width:
            return None
        remaining = w
        y = 0
        i = index
        while remaining > 0:
            if i >= len(self.segments):
                return None
            y = max(y, self.segments[i][1])
            if y + h > self.height:
                return None
            remaining -= self.segments[i][2]
            i += 1
        return y

    def insert(self, w: int, h: int) -> Optional[tuple[int, int]]:
        best = None
        for i in range(len(self.segments)):
            y = self._fit(i, w, h)
            if y is None:
                continue
            x = self.segments[i][0]
            score = (y + h, x)
            if best is None or score < best[0]:
                best = (score, i, x, y)
        if best is None:
            return None
        _score, index, x, y = best
        self._add(index, x, y, w, h)
        return x, y

    def _add(self, index: int, x: int, y: int, w: int, h: int) -> None:
        new = [x, y + h, w]
        self.segments.insert(index, new)
        i = index + 1
        while i < len(self.segments):
            seg = self.segments[i]
            prev = self.segments[i - 1]
            prev_end = prev[0] + prev[2]
            if seg[0] < prev_end:
                shrink = prev_end - seg[0]
                seg[0] += shrink
                seg[2] -= shrink
                if seg[2] <= 0:
                    self.segments.pop(i)
                    continue
                break
            break
        # funde segmentos vizinhos com a mesma altura
        merged = [self.segments[0]]
        for seg in self.segments[1:]:
            if seg[1] == merged[-1][1]:
                merged[-1][2] += seg[2]
            else:
                merged.append(seg)
        self.segments = merged


def pack(items: Iterable[PackItem], width: int, height: int, grouped: bool = True) -> Optional[dict[Hashable, tuple[int, int]]]:
    """Posiciona retângulos sem sobreposição. Retorna ``None`` se não couber."""
    items = list(items)
    if grouped:
        order = sorted(items, key=lambda it: (it.group, -it.height, -it.width, str(it.key)))
    else:
        order = sorted(items, key=lambda it: (-it.height, -it.width, it.group, str(it.key)))
    sky = _Skyline(width, height)
    out: dict[Hashable, tuple[int, int]] = {}
    for it in order:
        if it.width == 0 or it.height == 0:
            out[it.key] = (0, 0)
            continue
        pos = sky.insert(it.width, it.height)
        if pos is None:
            return None
        out[it.key] = pos
    return out


def pack_best(items: Sequence[PackItem], width: int, height: int) -> tuple[Optional[dict[Hashable, tuple[int, int]]], str]:
    """Tenta primeiro manter as partes agrupadas (atlas organizado); se não couber, prioriza espaço."""
    res = pack(items, width, height, grouped=True)
    if res is not None:
        return res, "agrupado por região"
    res = pack(items, width, height, grouped=False)
    if res is not None:
        return res, "ordenado por altura"
    return None, ""


def atlas_usage(items: Sequence[PackItem], width: int, height: int) -> float:
    return sum(it.width * it.height for it in items) / float(width * height)
