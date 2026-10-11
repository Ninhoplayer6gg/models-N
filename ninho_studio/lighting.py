"""Sombra de contato (oclusão ambiente) gravada na textura.

Para cada texel, lançamos raios no hemisfério da face e vemos quantos batem em outros
cubos por perto (no modelo já na pose). Lugares cercados de geometria — embaixo da
mandíbula, onde o pescoço encontra a cabeça, entre a perna e o corpo, entre os dedos,
dentro da boca — ficam mais escuros. É a "sombra" que um pixel artist pinta à mão,
calculada pela geometria de verdade e determinística (direções fixas, sem sorteio).
"""

from __future__ import annotations

import math

import numpy as np


def hemisphere_directions(count: int = 24) -> np.ndarray:
    """Direções fixas, com peso de cosseno, em volta de +Z (espiral)."""
    golden = math.pi * (3 - math.sqrt(5))
    out = []
    for i in range(count):
        r = math.sqrt((i + 0.5) / count)
        theta = i * golden
        x, y = r * math.cos(theta), r * math.sin(theta)
        z = math.sqrt(max(0.0, 1 - x * x - y * y))
        out.append((x, y, z))
    return np.array(out, dtype=float)


def _basis(n: np.ndarray) -> np.ndarray:
    n = n / np.linalg.norm(n)
    helper = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    t = np.cross(n, helper)
    t /= np.linalg.norm(t)
    b = np.cross(n, t)
    return np.stack([t, b, n])  # linhas


class OcclusionBaker:
    """Pré-calcula os cubos (já na pose) e responde a oclusão de cada texel."""

    def __init__(self, model, samples: int = 24, max_dist: float = 6.0):
        self.max_dist = float(max_dist)
        self.dirs = hemisphere_directions(samples)
        self.boxes = []
        for cube in model.iter_cubes():
            m = model.cube_matrix(cube)
            inv = np.linalg.inv(m)
            inf = float(cube.inflate)
            lo = np.array(cube.frm, dtype=float) - inf
            hi = np.array(cube.to, dtype=float) + inf
            corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
            world = corners @ m[:3, :3].T + m[:3, 3]
            self.boxes.append((inv, lo, hi, world.min(axis=0), world.max(axis=0)))

    def occlusion(self, points: np.ndarray, normal: np.ndarray) -> np.ndarray:
        """0 (aberto) .. 1 (fechado) para cada ponto de uma face."""
        if len(points) == 0:
            return np.zeros(0)
        n = normal / np.linalg.norm(normal)
        dirs = self.dirs @ _basis(n)  # (K, 3) no mundo
        origins = points + n * 0.02
        nearest = np.full((len(points), len(dirs)), np.inf)
        reach_lo = origins.min(axis=0) - self.max_dist
        reach_hi = origins.max(axis=0) + self.max_dist
        for inv, lo, hi, wlo, whi in self.boxes:
            if np.any(whi < reach_lo) or np.any(wlo > reach_hi):
                continue
            o = origins @ inv[:3, :3].T + inv[:3, 3]  # (N, 3) no sistema do cubo
            d = dirs @ inv[:3, :3].T  # (K, 3)
            d = np.where(np.abs(d) < 1e-12, 1e-12, d)
            inv_d = 1.0 / d
            t1 = (lo[None, None, :] - o[:, None, :]) * inv_d[None, :, :]
            t2 = (hi[None, None, :] - o[:, None, :]) * inv_d[None, :, :]
            tmin = np.minimum(t1, t2).max(axis=2)
            tmax = np.maximum(t1, t2).min(axis=2)
            hit = (tmax >= np.maximum(tmin, 0.0)) & (tmin < self.max_dist)
            nearest = np.minimum(nearest, np.where(hit, np.maximum(tmin, 0.0), np.inf))
        weight = np.clip(1.0 - nearest / self.max_dist, 0.0, 1.0)
        return weight.mean(axis=1)
