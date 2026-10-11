"""Faces de cubos diferentes no mesmo plano e viradas para o mesmo lado ("z-fighting").

Quando duas faces coincidem, a placa de vídeo escolhe qual mostrar pela ordem de desenho:
o resultado pisca no jogo e muda entre programas. O construtor resolve isso com um
``inflate`` mínimo (fração de pixel) num dos cubos; o validador avisa se sobrar algum caso.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np

from .geometry import transform_points
from .uv import FACE_NORMALS

# cantos de cada face de um cubo unitário (0..1), em ordem ao redor da face
_FACE_CORNERS = {
    "north": [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
    "south": [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    "west": [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)],
    "east": [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
    "down": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    "up": [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)],
}


def box_faces(matrix: np.ndarray, frm: Iterable[float], to: Iterable[float]) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """(face, normal no mundo, 4 cantos no mundo) de um cubo posicionado por ``matrix``."""
    lo = np.asarray(list(frm), dtype=float)
    hi = np.asarray(list(to), dtype=float)
    out = []
    for face, corners in _FACE_CORNERS.items():
        size = hi - lo
        axis = {"north": 2, "south": 2, "west": 0, "east": 0, "down": 1, "up": 1}[face]
        others = [i for i in range(3) if i != axis]
        if size[others[0]] <= 1e-9 or size[others[1]] <= 1e-9:
            continue
        pts = lo + np.asarray(corners, dtype=float) * size
        world = transform_points(matrix, pts)
        n = matrix[:3, :3] @ np.asarray(FACE_NORMALS[face], dtype=float)
        out.append((face, n / np.linalg.norm(n), world))
    return out


def _clip(subject: list[np.ndarray], a: np.ndarray, b: np.ndarray) -> list[np.ndarray]:
    """Sutherland–Hodgman: recorta o polígono pelo semiplano à esquerda de a→b (2D)."""
    def inside(p: np.ndarray) -> bool:
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

    def cross_point(p: np.ndarray, q: np.ndarray) -> np.ndarray:
        d1 = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        d2 = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        t = d1 / (d1 - d2)
        return p + t * (q - p)

    out: list[np.ndarray] = []
    for i in range(len(subject)):
        cur, prev = subject[i], subject[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(cross_point(prev, cur))
            out.append(cur)
        elif inside(prev):
            out.append(cross_point(prev, cur))
    return out


def _area(poly: list[np.ndarray]) -> float:
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def _ccw(poly: np.ndarray) -> list[np.ndarray]:
    c = poly.mean(axis=0)
    order = np.argsort(np.arctan2(poly[:, 1] - c[1], poly[:, 0] - c[0]))
    return [poly[i] for i in order]


def overlap_area(n: np.ndarray, p: np.ndarray, q: np.ndarray) -> float:
    """Área comum de dois quadriláteros convexos no mesmo plano (normal ``n``)."""
    u = np.cross(n, [1.0, 0.0, 0.0])
    if np.linalg.norm(u) < 0.5:
        u = np.cross(n, [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    P = _ccw(np.stack([p @ u, p @ v], axis=1))
    Q = _ccw(np.stack([q @ u, q @ v], axis=1))
    poly = P
    for i in range(len(Q)):
        poly = _clip(poly, Q[i - 1], Q[i])
        if not poly:
            return 0.0
    return _area(poly)


def find_overlaps(boxes: list[tuple[Any, np.ndarray, Any, Any]], min_area: float = 0.01,
                  plane_tol: float = 1e-3) -> list[tuple[Any, str, Any, str, float]]:
    """Pares de faces coplanares, viradas para o mesmo lado, que se sobrepõem.

    ``boxes``: (chave, matriz 4x4 do cubo na pose, from, to) — use from/to já com o inflate.
    """
    faces = []
    for key, matrix, frm, to in boxes:
        for face, n, pts in box_faces(matrix, frm, to):
            faces.append((key, face, n, float(n @ pts[0]), pts, pts.min(axis=0), pts.max(axis=0)))
    found = []
    for i in range(len(faces)):
        k1, f1, n1, d1, p1, lo1, hi1 = faces[i]
        for j in range(i + 1, len(faces)):
            k2, f2, n2, d2, p2, lo2, hi2 = faces[j]
            if k1 == k2 or float(n1 @ n2) < 1 - 1e-6 or abs(d1 - d2) > plane_tol:
                continue
            if np.any(hi1 < lo2 - 1e-6) or np.any(hi2 < lo1 - 1e-6):
                continue
            a = overlap_area(n1, p1, p2)
            if a > min_area:
                found.append((k1, f1, k2, f2, a))
    return found


def model_boxes(model) -> list[tuple[Any, np.ndarray, tuple, tuple]]:
    out = []
    for cube in model.iter_cubes():
        inf = float(cube.inflate)
        frm = tuple(v - inf for v in cube.frm)
        to = tuple(v + inf for v in cube.to)
        out.append((id(cube), model.cube_matrix(cube), frm, to))
    return out


def resolve_model(model, step: float = 0.05, max_rounds: int = 6) -> list[tuple[str, str]]:
    """Afasta faces coincidentes inflando o cubo menor (``step`` px por rodada). Devolve os pares tratados."""
    by_id = {id(c): c for c in model.iter_cubes()}
    fixed: list[tuple[str, str]] = []
    for _ in range(max_rounds):
        overlaps = find_overlaps(model_boxes(model))
        if not overlaps:
            break
        bumped: set[int] = set()
        for k1, _f1, k2, _f2, _a in overlaps:
            a, b = by_id[k1], by_id[k2]
            if id(a) in bumped or id(b) in bumped:
                continue
            vol = lambda c: c.size[0] * c.size[1] * c.size[2]  # noqa: E731
            target = a if (a.priority, -vol(a)) > (b.priority, -vol(b)) else b
            target.inflate = round(float(target.inflate) + step, 4)
            bumped.add(id(target))
            fixed.append((f"{a.bone}/{a.name}", f"{b.bone}/{b.name}"))
    return fixed


def bbmodel_overlaps(bbmodel: dict, min_area: float = 0.01) -> list[tuple[str, str, str, str, float]]:
    """Mesma conferência sobre o arquivo .bbmodel (nomes dos cubos e faces)."""
    from .geometry import pivot_matrix
    from .mesh import _adjusted_from_to

    groups = {g["uuid"]: g for g in bbmodel.get("groups", [])}
    parent_of: dict[str, Optional[str]] = {}

    def walk(nodes: list, parent: Optional[str]) -> None:
        for node in nodes:
            if isinstance(node, str):
                parent_of[node] = parent
            else:
                parent_of[node["uuid"]] = parent
                walk(node.get("children", []), node["uuid"])

    walk(bbmodel.get("outliner", []), None)
    cache: dict[str, np.ndarray] = {}

    def gmat(uid: Optional[str]) -> np.ndarray:
        if uid is None:
            return np.eye(4)
        if uid not in cache:
            g = groups[uid]
            cache[uid] = gmat(parent_of.get(uid)) @ pivot_matrix(g.get("origin", [0, 0, 0]), g.get("rotation", [0, 0, 0]))
        return cache[uid]

    boxes = []
    names = {}
    for el in bbmodel.get("elements", []):
        if el.get("type", "cube") != "cube":
            continue
        frm, to = _adjusted_from_to(el)
        m = gmat(parent_of.get(el["uuid"])) @ pivot_matrix(el.get("origin", [0, 0, 0]), el.get("rotation", [0, 0, 0]))
        boxes.append((el["uuid"], m, frm, to))
        names[el["uuid"]] = el.get("name", el["uuid"])
    return [(names[a], fa, names[b], fb, area) for a, fa, b, fb, area in find_overlaps(boxes, min_area=min_area)]
