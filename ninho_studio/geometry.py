"""Matemática de transformações com as mesmas convenções do Blockbench.

Conferido no código do Blockbench 5.2.2:

* rotações em graus, aplicadas como ``Math.degToRad`` sem inversão de sinal
  (``js/outliner/outliner.js`` → ``NodePreviewController.updateTransform``);
* ordem de Euler ``'ZYX'`` do three.js (``Format.euler_order``, padrão em
  ``js/io/format.ts``), que corresponde à matriz ``Rz · Ry · Rx``;
* cada grupo gira os filhos em torno de ``origin`` (coordenadas absolutas) e
  cada cubo gira em torno do próprio ``origin``.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

Vec3 = tuple[float, float, float]


def rot_x(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def rot_y(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)


def rot_z(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def euler_zyx(rotation: Sequence[float]) -> np.ndarray:
    """Matriz 3x3 para ``rotation = [rx, ry, rz]`` em graus (ordem three.js 'ZYX')."""
    rx, ry, rz = (float(v) for v in rotation)
    return rot_z(rz) @ rot_y(ry) @ rot_x(rx)


def pivot_matrix(origin: Sequence[float], rotation: Sequence[float]) -> np.ndarray:
    """Matriz 4x4 que gira em torno de ``origin``: T(o) · R · T(-o)."""
    m = np.eye(4)
    r = euler_zyx(rotation)
    o = np.asarray(origin, dtype=float)
    m[:3, :3] = r
    m[:3, 3] = o - r @ o
    return m


def transform_points(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=float)
    return pts @ m[:3, :3].T + m[:3, 3]


def transform_dirs(m: np.ndarray, dirs: np.ndarray) -> np.ndarray:
    return np.asarray(dirs, dtype=float) @ m[:3, :3].T


def chain_matrix(chain: Iterable[tuple[Sequence[float], Sequence[float]]]) -> np.ndarray:
    """Compõe uma cadeia de (origin, rotation) do pai mais externo ao mais interno."""
    m = np.eye(4)
    for origin, rotation in chain:
        m = m @ pivot_matrix(origin, rotation)
    return m


def snap(v: float, step: float = 0.5) -> float:
    """Arredonda para a grade de ``step`` (0,5 px por padrão)."""
    return round(v / step) * step


def snap3(v: Sequence[float], step: float = 0.5) -> Vec3:
    return (snap(v[0], step), snap(v[1], step), snap(v[2], step))


def clean_number(v: float) -> float | int:
    """Converte para int quando o valor é inteiro (JSON mais limpo e estável)."""
    v = float(v)
    if abs(v - round(v)) < 1e-9:
        return int(round(v))
    return round(v, 4)
