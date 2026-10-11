"""Textura procedural (etapa PROCEDURAL, sem IA).

Cada texel do atlas pertence a uma face de um cubo. Para cada um calculamos o
ponto 3D correspondente (``uv.uv_to_local``, igual ao Blockbench) e a posição
na pose final. As regras de pintura usam essas informações para criar regiões
intencionais:

* contra-sombreamento: dorso mais escuro, laterais, ventre mais claro;
* escamas ventrais na barriga, linha dos lábios, céu da boca e língua;
* olhos com pupila e sobrancelha, narinas, dentes pontudos, garras e unhas;
* padrões opcionais (listras, manchas, faixas, mosqueado) calculados em 3D
  para continuarem de uma peça para outra;
* microtextura do material (escamas, pele rugosa, lisa, penas).

Tudo é feito com uma paleta discreta (rampas de tons) e sem filtragem, para
manter os pixels nítidos.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import numpy as np

from .geometry import transform_points
from .model import Cube, Model
from .palette import Ramp, detail_dark, hex_to_rgb, light_factor, mix
from .uv import FACE_NORMALS, FACES, box_uv_face_rects, rect_bounds, uv_to_local

BELLY_PARTS = {"pelvis", "torso", "chest", "neck", "tail", "jaw"}
LIMB_PARTS = {"thigh", "shin", "metatarsus", "upper_arm", "forearm", "foot"}
PATTERN_PARTS = {"pelvis", "torso", "chest", "neck", "tail", "skull", "snout", "thigh", "upper_arm"}
RIM_PARTS = {"pelvis", "torso", "neck", "skull", "snout", "tail"}
PRIMARY, SECONDARY, BELLY, PATTERN = range(4)


@dataclass
class FaceTexels:
    cube: Cube
    face: str
    ii: np.ndarray  # coluna no atlas (pixels)
    jj: np.ndarray  # linha no atlas
    rest: np.ndarray  # (N, 3) ponto em repouso
    world: np.ndarray  # (N, 3) ponto na pose final
    normal: np.ndarray  # (3,) normal na pose final
    rel: np.ndarray  # (N, 3) posição relativa dentro do cubo (0..1)
    col: np.ndarray  # coluna dentro da face (0 = esquerda vista de fora)
    row: np.ndarray  # linha dentro da face (0 = topo)
    fw: int
    fh: int


def face_texels(model: Model, cube: Cube) -> list[FaceTexels]:
    rects = box_uv_face_rects(cube.frm, cube.to, cube.uv_offset, cube.mirror_uv)
    m = model.cube_matrix(cube)
    size = np.array(cube.size, dtype=float)
    safe = np.where(size == 0, 1.0, size)
    out = []
    for face in FACES:
        uv = rects[face]
        u0, v0, u1, v1 = rect_bounds(uv)
        fw, fh = int(round(u1 - u0)), int(round(v1 - v0))
        if fw <= 0 or fh <= 0:
            continue
        ii, jj = np.meshgrid(np.arange(int(u0), int(u0) + fw), np.arange(int(v0), int(v0) + fh))
        ii = ii.ravel()
        jj = jj.ravel()
        rest = uv_to_local(face, uv, cube.frm, cube.to, ii + 0.5, jj + 0.5)
        world = transform_points(m, rest)
        normal = m[:3, :3] @ np.array(FACE_NORMALS[face])
        rel = (rest - np.array(cube.frm)) / safe
        # coordenadas "vistas de fora": coluna da esquerda para a direita, linha de cima para baixo
        du = 1 if uv[2] >= uv[0] else -1
        dv = 1 if uv[3] >= uv[1] else -1
        col = (ii - int(round(min(uv[0], uv[2])))) if du > 0 else (int(round(max(uv[0], uv[2]))) - 1 - ii)
        row = (jj - int(round(min(uv[1], uv[3])))) if dv > 0 else (int(round(max(uv[1], uv[3]))) - 1 - jj)
        out.append(FaceTexels(cube, face, ii, jj, rest, world, normal, rel, col, row, fw, fh))
    return out


# ---------------------------------------------------------------------------
# Ruído estruturado (determinístico)
# ---------------------------------------------------------------------------


def _hash3(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, seed: int) -> np.ndarray:
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791)
    h = (h ^ (seed * 2654435761)) & 0xFFFFFFFF
    h = h.astype(np.uint64)
    h ^= h >> np.uint64(16)
    h = (h * np.uint64(0x7FEB352D)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(15)
    h = (h * np.uint64(0x846CA68B)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(16)
    return h.astype(np.float64) / float(0xFFFFFFFF)


def value_noise3(p: np.ndarray, freq: float, seed: int) -> np.ndarray:
    q = p * freq
    base = np.floor(q)
    f = q - base
    f = f * f * (3 - 2 * f)
    ix, iy, iz = base[:, 0], base[:, 1], base[:, 2]
    acc = np.zeros(len(p))
    for dx in (0, 1):
        wx = f[:, 0] if dx else 1 - f[:, 0]
        for dy in (0, 1):
            wy = f[:, 1] if dy else 1 - f[:, 1]
            for dz in (0, 1):
                wz = f[:, 2] if dz else 1 - f[:, 2]
                acc += wx * wy * wz * _hash3(ix + dx, iy + dy, iz + dz, seed)
    return acc


# ---------------------------------------------------------------------------
# Pintor
# ---------------------------------------------------------------------------


class ProceduralPainter:
    def __init__(self, model: Model, spec: dict[str, Any], seed: int):
        self.model = model
        self.spec = spec
        self.seed = int(seed)
        c = spec["colors"]
        self.primary = Ramp(c["primary"])
        self.secondary = Ramp(c["secondary"])
        self.belly = Ramp(c["belly"])
        self.pattern = Ramp(c["pattern"])
        self.eyes = Ramp(c["eyes"])
        self.claws = Ramp(c["claws"])
        self.mouth = Ramp(c["mouth"])
        self.pattern_type = spec["pattern"]["type"]
        self.intensity = float(spec["pattern"]["intensity"])
        self.skin = spec["skin"]
        self.features = spec["features"]
        self.has_toe_claws = any(cb.part == "toe_claw" for cb in model.iter_cubes())
        # rampas na ordem PRIMARY, SECONDARY, BELLY, PATTERN: (4, 8, 3), indexadas por nível + 4
        self._ramps = np.stack([r.array() for r in (self.primary, self.secondary, self.belly, self.pattern)])
        prim = hex_to_rgb(c["primary"])
        # cor escura de detalhe (contorno do olho, narinas, dedos) com contraste garantido
        self.detail_rgb = np.array(detail_dark(prim), dtype=np.int32)
        # linha dos lábios: em cores muito claras um tom de detalhe suave, senão o tom -2
        if light_factor(prim) > 0.5:
            self.lip_rgb = np.array(mix(prim, detail_dark(prim), 0.55), dtype=np.int32)
        else:
            self.lip_rgb = np.array(self.primary[-2], dtype=np.int32)
        self._prepare_patterns()

    # -- padrões globais (dependem só da seed e da forma geral) ---------------
    def _prepare_patterns(self) -> None:
        rng = random.Random(f"{self.seed}:pattern")
        cubes = [c for c in self.model.iter_cubes() if c.part in PATTERN_PARTS]
        lo, hi = self.model.world_bounds(cubes) if cubes else (np.zeros(3), np.ones(3))
        s = float(self.spec["scale"])
        self.stripes: list[tuple[float, float, float, float]] = []  # (z_centro, largura, alcance, inclinação)
        z = float(lo[2]) + rng.uniform(6.0, 9.0) * s
        while z < hi[2]:
            width = rng.choice((1.0, 1.0, 1.0, 1.5, 2.0)) * (0.8 + 0.4 * self.intensity)
            reach = rng.uniform(0.40, 0.80) * (0.55 + 0.5 * self.intensity)
            slant = rng.uniform(0.6, 2.0)
            self.stripes.append((z, width, min(0.95, reach), slant))
            z += rng.uniform(4.5, 7.5) * s * (1.3 - 0.4 * self.intensity)
        self.band_period = max(4.0, 7.0 * s * (1.2 - 0.4 * self.intensity))
        self.spot_centers: np.ndarray | None = None
        self.scars: list[tuple[str, int, int, int, int]] = []

    # -- utilidades -------------------------------------------------------------
    @staticmethod
    def _put(img: np.ndarray, ft: FaceTexels, rgb: np.ndarray) -> None:
        img[ft.jj, ft.ii, :3] = rgb
        img[ft.jj, ft.ii, 3] = 255

    def _ramp_pick(self, ramp: Ramp, levels: np.ndarray) -> np.ndarray:
        arr = ramp.array()
        return arr[np.clip(levels, -4, 3) + 4]

    # -- zonas de pele ------------------------------------------------------------
    def _skin_zone(self, ft: FaceTexels) -> np.ndarray:
        """0 = dorso, 1 = lateral alta, 2 = lateral baixa, 3 = ventre."""
        n = len(ft.ii)
        part = ft.cube.part
        ny = ft.normal[1]
        ry = ft.rel[:, 1]
        zone = np.ones(n, dtype=int)
        if ny > 0.6:
            zone[:] = 0
        elif ny < -0.6:
            zone[:] = 3 if part in BELLY_PARTS else 2
        elif part in LIMB_PARTS:
            # membros: cor principal uniforme, só a borda de cima um pouco mais escura
            zone = np.where(ry > 0.85, 0, 1)
        else:
            zone = np.where(ry > 0.62, 0, np.where(ry > 0.40, 1, 2))
            if part in BELLY_PARTS:
                belly_line = 0.30 if part != "jaw" else 0.55
                zone = np.where(ry < belly_line, 3, zone)
        return zone

    def _paint_skin(self, ft: FaceTexels) -> np.ndarray:
        """Pele por tons da paleta: cada regra soma ou subtrai níveis da rampa (sem multiplicar cores)."""
        zone = self._skin_zone(ft)
        part = ft.cube.part
        side = abs(ft.normal[1]) < 0.6
        ramp = np.where(zone == 3, BELLY, np.where(zone == 2, SECONDARY, PRIMARY))
        # ajustes estruturais: tom inteiro da rampa
        level = np.where(zone == 0, -1, 0)
        # parte de baixo das pernas um tom mais escura
        if part in ("metatarsus", "foot"):
            level = level - 1
        # escamas ventrais: linhas transversais na barriga
        if part in BELLY_PARTS and ft.normal[1] < -0.6:
            level = level - ((np.floor(ft.world[:, 2]).astype(int) % 2) == 0)
        # sombra na base das pernas/braços
        if part in ("thigh", "shin", "metatarsus", "upper_arm") and side:
            level = level - (ft.row == ft.fh - 1)

        # ajustes de textura: 40% do caminho até o tom vizinho (sutis em qualquer cor)
        touch = self._micro_levels(ft, zone)
        if part in RIM_PARTS and side:  # luz de borda no alto das laterais (volume)
            touch = touch + ((ft.row == 0) & (zone <= 1))
        if part in ("shin", "metatarsus") and ft.face == "north":  # escamas na frente da canela
            touch = touch - (ft.row % 2 == 1)
        touch = np.clip(touch, -1, 1)

        full = soft = None
        if part in PATTERN_PARTS and self.pattern_type != "none":
            full, soft = self._pattern_masks(ft, zone)
            ramp = np.where(full, PATTERN, ramp)
            level = np.where(full, 0, level)
            touch = np.where(full, 0, touch)

        base = self._ramps[ramp, np.clip(level, -4, 3) + 4].astype(np.int32)
        alt = self._ramps[ramp, np.clip(level + touch, -4, 3) + 4].astype(np.int32)
        rgb = base + ((alt - base) * 2) // 5

        # faixa de transição nítida entre lateral e ventre (tom intermediário, sem pontilhado)
        if side and part in BELLY_PARTS:
            ry = ft.rel[:, 1]
            belly_line = 0.30 if part != "jaw" else 0.55
            texel = 1.0 / max(1, ft.fh)
            edge = (ry >= belly_line) & (ry < belly_line + texel * 1.01)
            if full is not None:
                edge &= ~full
            mid = (self._ramps[SECONDARY, 4].astype(np.int32) + self._ramps[BELLY, 4].astype(np.int32)) // 2
            rgb[edge] = mid
        # perto da barriga o padrão fica mais suave (metade do tom)
        if soft is not None and soft.any():
            rgb[soft] = (rgb[soft] + self._ramps[PATTERN, 4].astype(np.int32)) // 2
        return rgb

    def _micro_levels(self, ft: FaceTexels, zone: np.ndarray) -> np.ndarray:
        """Microtextura do material: +1 tom (brilho) ou -1 tom (sombra) por texel."""
        i, j = ft.col, ft.row
        n = len(i)
        delta = np.zeros(n, dtype=int)
        if self.skin == "smooth":
            return delta
        if self.skin == "scales":
            stagger = (j // 2) % 2 * 2
            up = (j % 2 == 0) & ((i + stagger) % 4 == 0)
            down = (j % 2 == 1) & ((i + stagger) % 4 == 1)
        elif self.skin == "rough":
            nz = value_noise3(ft.world, 0.55, self.seed + 11)
            up = nz > 0.80
            down = nz < 0.22
        else:  # feathered
            w = ft.world
            chevron = (np.floor(w[:, 2] * 0.9 + np.abs(w[:, 0]) * 0.8) % 3) == 0
            up = chevron & (zone <= 1)
            down = (~chevron) & (zone <= 1) & ((i + j) % 5 == 0)
        delta[up] += 1
        delta[down] -= 1
        return delta

    def _dorsal_distance(self, ft: FaceTexels) -> np.ndarray:
        """0 na linha média do dorso, ~1 na linha da barriga."""
        rel = ft.rel
        if ft.normal[1] > 0.6:
            return 0.32 * np.abs(2 * rel[:, 0] - 1)
        if ft.normal[1] < -0.6:
            return np.full(len(rel), 1.2)
        return 0.32 + 0.68 * (1 - rel[:, 1])

    def _pattern_masks(self, ft: FaceTexels, zone: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Texels do padrão: (cor cheia, cor suavizada perto da barriga)."""
        n = len(ft.ii)
        mask = np.zeros(n, dtype=bool)
        d = self._dorsal_distance(ft)
        z = ft.world[:, 2]
        part = ft.cube.part
        if self.pattern_type == "stripes":
            if part not in ("upper_arm",):
                for zc, width, reach, slant in self.stripes:
                    local_reach = reach * (0.75 if part in ("skull", "snout", "thigh") else 1.0)
                    taper = np.clip(1 - (d / max(local_reach, 1e-3)) ** 2, 0, 1)
                    half = width / 2 * np.sqrt(taper)
                    mask |= (np.abs(z - zc - slant * d * 2.0) <= half) & (d < local_reach)
        elif self.pattern_type == "spots":
            centers = self._spots()
            if centers is not None and len(centers):
                diff = ft.world[:, None, :] - centers[None, :, :3]
                dist = np.sqrt((diff ** 2).sum(axis=2))
                mask = (dist <= centers[None, :, 3]).any(axis=1) & (d < 1.0)
        elif self.pattern_type == "bands":
            if part in ("tail", "neck", "thigh", "upper_arm"):
                width = 0.35 + 0.25 * self.intensity
                phase = (z / self.band_period) % 1.0
                mask = phase < width
            elif part in ("torso", "pelvis"):
                phase = (z / self.band_period) % 1.0
                mask = (phase < 0.25 + 0.2 * self.intensity) & (d < 0.6)
        elif self.pattern_type == "mottled":
            nz = value_noise3(ft.world, 0.16, self.seed + 3) * 0.75 + value_noise3(ft.world, 0.45, self.seed + 5) * 0.25
            mask = (nz > 0.66 - 0.18 * self.intensity) & (d < 0.95)
        soft = mask & ((zone == 2) | (zone == 3))
        return mask & ~soft, soft

    def _spots(self) -> np.ndarray | None:
        if self.spot_centers is not None:
            return self.spot_centers
        rng = random.Random(f"{self.seed}:spots")
        candidates = []
        for cube in self.model.iter_cubes():
            if cube.part not in PATTERN_PARTS:
                continue
            for ft in face_texels(self.model, cube):
                if ft.normal[1] < -0.6:
                    continue
                d = self._dorsal_distance(ft)
                keep = d < 0.9
                candidates.extend(ft.world[keep].tolist())
        rng.shuffle(candidates)
        s = float(self.spec["scale"])
        min_dist = (3.4 - 1.2 * self.intensity) * s
        chosen: list[list[float]] = []
        for p in candidates:
            if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 >= min_dist ** 2 for q in chosen):
                radius = rng.choice((0.55, 0.75, 0.75, 1.05, 1.3)) * (0.8 + 0.5 * self.intensity) * max(0.8, s)
                chosen.append([p[0], p[1], p[2], radius])
            if len(chosen) > 400:
                break
        self.spot_centers = np.array(chosen) if chosen else np.zeros((0, 4))
        return self.spot_centers

    # -- partes especiais -----------------------------------------------------------
    def _paint_mouth(self, ft: FaceTexels, roof: bool) -> np.ndarray:
        n = len(ft.ii)
        rgb = self._ramp_pick(self.mouth, np.zeros(n, dtype=int)).astype(np.int32)
        if roof:
            ridges = (ft.row % 2) == 1
            rgb[ridges] = self._ramp_pick(self.mouth, np.full(n, -1))[ridges]
        else:
            center = np.abs(2 * ft.rel[:, 0] - 1) < 0.5
            rgb[center] = self._ramp_pick(self.mouth, np.full(n, 1))[center]
        return rgb

    def _paint_teeth(self, ft: FaceTexels) -> np.ndarray:
        n = len(ft.ii)
        gum = self._ramp_pick(self.mouth, np.full(n, -1)).astype(np.int32)
        tooth = self._ramp_pick(self.claws, np.zeros(n, dtype=int))
        tooth_shadow = self._ramp_pick(self.claws, np.full(n, -1))
        rgb = gum.copy()
        kind = ft.cube.tags.get("teeth")
        if ft.face in ("up", "down", "south"):
            return rgb
        r = ft.row
        c = ft.col
        if kind == "upper":
            base = r == ft.fh - 2
            tip = (r == ft.fh - 1) & (c % 2 == 0)
            rgb[base] = tooth_shadow[base]
            rgb[tip] = tooth[tip]
            rgb[base & (c % 2 == 0)] = tooth[base & (c % 2 == 0)]
        else:
            base = r == 1
            tip = (r == 0) & (c % 2 == 0)
            rgb[base] = tooth_shadow[base]
            rgb[tip] = tooth[tip]
            rgb[base & (c % 2 == 0)] = tooth[base & (c % 2 == 0)]
        return rgb

    def _paint_claw(self, ft: FaceTexels) -> np.ndarray:
        n = len(ft.ii)
        if ft.cube.part == "toe_claw":
            t = 1 - ft.rel[:, 2]  # ponta para a frente (-Z)
        else:
            t = 1 - ft.rel[:, 1]  # ponta para baixo
        levels = np.where(t > 0.66, -2, np.where(t > 0.33, -1, 0))
        rgb = self._ramp_pick(self.claws, levels).astype(np.int32)
        if ft.face == "up":
            rgb = self._ramp_pick(self.claws, np.full(n, 1)).astype(np.int32)
        return rgb

    def _paint_spike(self, ft: FaceTexels) -> np.ndarray:
        n = len(ft.ii)
        levels = np.where(ft.rel[:, 1] > 0.5, 1, -1)
        if ft.face == "up":
            levels = np.full(n, 1)
        return self._ramp_pick(self.pattern, levels).astype(np.int32)

    def _paint_crest(self, ft: FaceTexels) -> np.ndarray:
        n = len(ft.ii)
        stripes = (ft.col + ft.row) % 3 == 0
        rgb = self._ramp_pick(self.pattern, np.zeros(n, dtype=int)).astype(np.int32)
        rgb[stripes] = self._ramp_pick(self.secondary, np.full(n, 1))[stripes]
        return rgb

    def _paint_brow(self, ft: FaceTexels) -> np.ndarray:
        n = len(ft.ii)
        if ft.cube.tags.get("horn"):
            levels = np.where(ft.rel[:, 1] > 0.66, -1, -3)
            return self._ramp_pick(self.primary, levels).astype(np.int32)
        levels = np.full(n, -2)
        if ft.face == "up":
            levels = np.full(n, -1)
        return self._ramp_pick(self.primary, levels).astype(np.int32)

    def _paint_foot(self, ft: FaceTexels, rgb: np.ndarray) -> np.ndarray:
        n = len(ft.ii)
        if ft.face == "down":
            return self._ramp_pick(self.primary, np.full(n, -3)).astype(np.int32)
        toes = int(ft.cube.tags.get("toes", 3))
        rx = ft.rel[:, 0]
        boundaries = [k / toes for k in range(1, toes)]
        sep = np.zeros(n, dtype=bool)
        fwidth = max(1.0, ft.cube.size[0])
        for b in boundaries:
            sep |= np.abs(rx - b) < (0.5 / fwidth)
        if ft.face == "up":
            front = ft.rel[:, 2] < 0.6
            rgb[sep & front] = self.detail_rgb
        if ft.face == "north":
            rgb[sep] = self.detail_rgb
            if not self.has_toe_claws:
                nails = (ft.row == ft.fh - 1) & ~sep
                rgb[nails] = self._ramp_pick(self.claws, np.full(n, -1))[nails]
        return rgb

    def _paint_eye(self, img: np.ndarray, ft: FaceTexels, rgb: np.ndarray) -> np.ndarray:
        for lm in self.model.landmarks.values():
            if not lm.name.startswith("eye_") or lm.bone != ft.cube.bone or lm.cube != ft.cube.name or lm.face != ft.face:
                continue
            # a = deslocamento para a frente (focinho, -Z); b = para cima
            a = np.floor(lm.point[2] - ft.rest[:, 2]).astype(int)
            b = np.floor(ft.rest[:, 1] - lm.point[1]).astype(int)
            n = len(ft.ii)
            iris = self._ramp_pick(self.eyes, np.zeros(n, dtype=int))
            iris_light = self._ramp_pick(self.eyes, np.full(n, 2))
            pupil = np.tile(np.array([[18, 14, 12]]), (n, 1))
            brow = np.tile(self.detail_rgb, (n, 1))
            lid = self._ramp_pick(self.primary, np.full(n, -2))
            rules = [
                ((b == 1) & (a >= -2) & (a <= 1), brow),
                ((b == -2) & (a >= -1) & (a <= 0), lid),
                ((a == 1) & (b >= -1) & (b <= 0), lid),
                ((a == -1) & (b == 0), iris_light),
                ((a == -1) & (b == -1), iris),
                ((a == 0) & (b >= -1) & (b <= 0), pupil),
            ]
            for cond, color in rules:
                rgb[cond] = color[cond]
        return rgb

    def _paint_nostrils(self, ft: FaceTexels, rgb: np.ndarray) -> np.ndarray:
        for lm in self.model.landmarks.values():
            if not lm.name.startswith("nostril_") or lm.cube != ft.cube.name or lm.face != ft.face:
                continue
            dx = np.abs(ft.rest[:, 0] - lm.point[0])
            dz = np.abs(ft.rest[:, 2] - lm.point[2])
            hit = (dx < 0.75) & (dz < 0.75)
            rgb[hit] = self.detail_rgb
        return rgb

    def _paint_lips(self, ft: FaceTexels, rgb: np.ndarray) -> np.ndarray:
        part = ft.cube.part
        if ft.face in ("up", "down"):
            return rgb
        n = len(ft.ii)
        if part in ("snout", "skull") and ft.face != "south":
            rgb[ft.row == ft.fh - 1] = self.lip_rgb
        if part == "jaw" and ft.face != "south":
            rgb[ft.row == 0] = self.lip_rgb
        return rgb

    def _paint_scars(self, ft: FaceTexels, rgb: np.ndarray) -> np.ndarray:
        if not self.features.get("scars"):
            return rgb
        if ft.cube.part not in ("torso", "snout", "skull") or ft.face not in ("east", "west"):
            return rgb
        rng = random.Random(f"{self.seed}:scar:{ft.cube.bone}:{ft.cube.name}:{ft.face}")
        n = len(ft.ii)
        light = self._ramp_pick(self.belly, np.full(n, 1))
        count = 2 if ft.cube.part == "torso" else 1
        for _ in range(count):
            c0 = rng.randrange(1, max(2, ft.fw - 4))
            r0 = rng.randrange(1, max(2, ft.fh // 2))
            length = rng.randint(3, 5)
            for k in range(length):
                hit = (ft.col == c0 + k) & (ft.row == r0 + k // 2)
                rgb[hit] = light[hit]
        return rgb

    # -- principal -------------------------------------------------------------------
    def paint(self) -> np.ndarray:
        img = np.zeros((self.model.texture_height, self.model.texture_width, 4), dtype=np.uint8)
        for cube in self.model.iter_cubes():
            for ft in face_texels(self.model, cube):
                rgb = self._paint_face(img, ft)
                self._put(img, ft, np.clip(rgb, 0, 255).astype(np.uint8))
        return img

    def _paint_face(self, img: np.ndarray, ft: FaceTexels) -> np.ndarray:
        part = ft.cube.part
        material = ft.cube.material
        if material == "teeth":
            return self._paint_teeth(ft)
        if material == "claw":
            return self._paint_claw(ft)
        if material == "spike":
            return self._paint_spike(ft)
        if material == "crest":
            return self._paint_crest(ft)
        if part == "brow":
            return self._paint_brow(ft)
        if part in ("skull", "snout") and ft.face == "down":
            return self._paint_mouth(ft, roof=True)
        if part == "jaw" and ft.face == "up":
            return self._paint_mouth(ft, roof=False)
        rgb = self._paint_skin(ft)
        if part == "foot":
            rgb = self._paint_foot(ft, rgb)
        if part == "nasal_ridge":
            rgb = self._ramp_pick(self.primary, np.full(len(ft.ii), -1 if ft.face != "up" else 0)).astype(np.int32)
        rgb = self._paint_lips(ft, rgb)
        rgb = self._paint_eye(img, ft, rgb)
        rgb = self._paint_nostrils(ft, rgb)
        rgb = self._paint_scars(ft, rgb)
        return rgb


def paint_texture(model: Model, spec: dict[str, Any], seed: int) -> np.ndarray:
    """Gera a textura RGBA (altura x largura x 4) para um modelo com UVs já atribuídas."""
    return ProceduralPainter(model, spec, seed).paint()
