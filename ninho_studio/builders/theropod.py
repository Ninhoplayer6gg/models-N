"""Construtor procedural de terópodes (base ajustável de T-rex).

O modelo é montado em pose de repouso alinhada aos eixos (como o Blockbench
guarda os cubos) e a postura vem das rotações dos ossos, cada um com o pivô
na articulação correspondente — pronto para animação futura.

Hierarquia::

    root
    └── body (quadril/pelve)
        ├── torso
        │   ├── neck
        │   │   └── head
        │   │       └── jaw
        │   ├── arm_right ── forearm_right
        │   └── arm_left ─── forearm_left
        ├── tail_1 ── tail_2 ── ... (3 a 5 segmentos)
        ├── leg_right ── shin_right ── [metatarsus_right] ── foot_right
        └── leg_left ─── shin_left ─── [metatarsus_left] ─── foot_left
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Any, Optional

import numpy as np

from ..geometry import snap
from ..model import Landmark, Model
from ..spec import BuildSettings

# Regiões do atlas (ordem de empacotamento)
REGION_HEAD, REGION_BODY, REGION_TAIL, REGION_LEGS, REGION_ARMS = range(5)


@dataclass(frozen=True)
class Structure:
    tail_segments: int
    metatarsus: bool
    jaw_split: bool
    chest: bool
    teeth: bool


STRUCTURE_BY_DETAIL = {
    "low": Structure(tail_segments=3, metatarsus=False, jaw_split=False, chest=False, teeth=True),
    "medium": Structure(tail_segments=4, metatarsus=True, jaw_split=True, chest=True, teeth=True),
    "high": Structure(tail_segments=5, metatarsus=True, jaw_split=True, chest=True, teeth=True),
}

# Detalhes opcionais: (nome, prioridade, níveis de detalhe que o permitem)
EXTRAS = [
    ("brows", 1, ("medium", "high")),
    ("toe_claws", 2, ("high",)),
    ("nasal_ridge", 2, ("high",)),
    ("back_spikes", 2, ("medium", "high")),
    ("feather_crest", 2, ("medium", "high")),
]


class BudgetError(ValueError):
    def __init__(self, needed: int, budget: int):
        self.needed = needed
        self.budget = budget
        super().__init__(
            f"orçamento de elementos insuficiente: o T-rex mínimo precisa de {needed} cubos e o orçamento é {budget}"
        )


def _box(cx: float, cy: float, cz: float, w: int, h: int, d: int) -> tuple[tuple[float, float, float], tuple[int, int, int]]:
    """Cubo centrado em (cx, cy, cz) com tamanho inteiro; posição na grade de 0,5."""
    frm = (snap(cx - w / 2.0), snap(cy - h / 2.0), snap(cz - d / 2.0))
    return frm, (int(w), int(h), int(d))


def _distribute(total: float, weights: list[float]) -> list[int]:
    s = sum(weights)
    raw = [total * w / s for w in weights]
    out = [max(2, int(round(r))) for r in raw]
    return out


def build_theropod(
    spec: dict[str, Any],
    settings: BuildSettings,
    structure: Optional[Structure] = None,
    extras: Optional[set[str]] = None,
) -> Model:
    """Monta o modelo para uma estrutura e um conjunto de extras fixos."""
    detail = spec["detail_level"]
    structure = structure or STRUCTURE_BY_DETAIL[detail]
    if extras is None:
        extras = {name for name, _prio, levels in EXTRAS if detail in levels}
    features = spec["features"]
    P = spec["proportions"]
    s = float(spec["scale"])
    rng = random.Random(f"{settings.seed}:pose")

    def I(v: float, minimum: int = 1) -> int:
        return max(minimum, int(round(v * s)))

    def jitter(amount: float) -> float:
        return rng.uniform(-amount, amount)

    def ang(a: float) -> float:
        """Ângulos em passos de 0,5° (valores limpos e somas exatas na perna)."""
        return round(a * 2.0) / 2.0

    model = Model(name=spec.get("name") or "T-rex", texture_size=settings.texture_size)
    model.meta["structure"] = structure.__dict__.copy()
    model.meta["extras"] = sorted(extras)

    bulk = P["body_bulk"]
    blen = P["body_length"]
    hs = P["head_size"]

    # ---------------- dimensões ----------------
    pel_w, pel_h, pel_l = I(10 * bulk, 4), I(13 * bulk, 4), I(9 * blen, 4)
    tor_w, tor_h, tor_l = I(12 * bulk, 4), I(15 * bulk, 4), I(14 * blen, 4)
    neck_factor = 0.6 * bulk + 0.4 * hs
    neck_w, neck_h, neck_l = I(8 * neck_factor, 3), I(10 * neck_factor, 3), I(9 * P["neck_length"], 3)
    cr_w, cr_h, cr_l = I(10 * hs, 4), I(9 * hs, 4), I(10 * hs, 4)
    sn_w = min(I(8 * hs, 3), cr_w - 2)
    sn_h = min(I(6 * hs, 3), cr_h - 2)
    sn_l = I(8 * hs * P["snout_length"], 3)
    jaw_h = I(3 * hs, 2)

    al = P["arm_length"]
    arm_t = I(2 * (0.75 + 0.25 * bulk), 1)
    ua_len = I(4 * al, 2)
    fa_len = I(4 * al, 2)

    ll, lt = P["leg_length"], P["leg_thickness"]
    th_w, th_len, th_d = I(6 * lt * (0.85 + 0.15 * bulk), 3), I(14 * ll, 6), I(9 * lt, 4)
    sh_w, sh_len, sh_d = I(4 * lt, 2), I(11 * ll, 4), I(5 * lt, 2)
    mt_w, mt_len, mt_d = I(3 * lt, 2), I(7 * ll, 3), I(4 * lt, 2)
    ft_w, ft_h, ft_l = I(6 * lt, 3), I(2 * lt, 2), I(9 * (0.6 + 0.4 * lt), 4)
    if not structure.metatarsus:
        sh_len += max(1, mt_len - 2)

    # ---------------- postura (graus) ----------------
    torso_pitch = ang(-4.0 + jitter(1.0))
    neck_pitch = ang(36.0 + 4.0 * (P["neck_length"] - 1.0) + jitter(2.0))
    head_world = ang(3.0 + jitter(2.0))
    head_pitch = head_world - (torso_pitch + neck_pitch)
    jaw_pitch = ang(-30.0 * P["jaw_open"])
    thigh_pitch = ang(24.0 + jitter(1.5))
    shin_pitch = ang(-60.0 + jitter(1.5))
    meta_pitch = 48.0
    arm_pitch = ang(25.0 + jitter(4.0))
    arm_roll = 12.0
    forearm_pitch = ang(-55.0 + jitter(4.0))

    # ---------------- ossos e cubos ----------------
    H = (0.0, 0.0, 0.0)  # articulação do quadril (ajustada depois para o chão)
    model.add_bone("root", (0.0, 0.0, 0.0))
    model.add_bone("body", H, parent="root")

    # pelve
    pel_y0 = -round(pel_h * 0.42)
    pel_z0 = -round(pel_l * 0.55)
    model.add_cube("body", "pelvis", (-pel_w / 2, pel_y0, pel_z0), (pel_w, pel_h, pel_l), "pelvis",
                   tags={"belly": True, "region": REGION_BODY, "axis": "z"})
    pel_top = pel_y0 + pel_h
    pel_front = pel_z0
    pel_back = pel_z0 + pel_l

    # tronco
    T = (0.0, snap(pel_top - 5), snap(pel_front + 1))
    model.add_bone("torso", T, (torso_pitch, 0, 0), parent="body")
    tor_y0 = pel_top - tor_h
    tor_z0 = T[2] - tor_l
    model.add_cube("torso", "torso", (snap(-tor_w / 2), tor_y0, tor_z0), (tor_w, tor_h, tor_l + 2), "torso",
                   tags={"belly": True, "region": REGION_BODY, "axis": "z"})
    tor_front = tor_z0
    if structure.chest:
        ch_w = max(3, tor_w - 3)
        ch_l = max(4, int(round(tor_l * 0.55)))
        frm, size = _box(0, tor_y0 - 1.5, tor_front + 2 + ch_l / 2, ch_w, 5, ch_l)
        model.add_cube("torso", "chest", frm, size, "chest", tags={"belly": True, "region": REGION_BODY, "axis": "z"})

    # pescoço
    N = (0.0, snap(pel_top - 3), snap(tor_front + 2.5))
    model.add_bone("neck", N, (neck_pitch, 0, 0), parent="torso")
    neck_y0 = snap(N[1] - neck_h * 0.6)
    model.add_cube("neck", "neck", (snap(-neck_w / 2), neck_y0, N[2] - neck_l), (neck_w, neck_h, neck_l + 2), "neck",
                   tags={"belly": True, "region": REGION_BODY, "axis": "z"})

    # cabeça
    Hd = (0.0, snap(N[1] + 0.5), snap(N[2] - neck_l + 1.5))
    model.add_bone("head", Hd, (head_pitch, 0, 0), parent="neck")
    head_bottom = Hd[1] - 2.5
    cr_front = Hd[2] - (cr_l - 2)
    model.add_cube("head", "skull", (snap(-cr_w / 2), head_bottom, cr_front), (cr_w, cr_h, cr_l), "skull",
                   tags={"region": REGION_HEAD, "axis": "z"})
    sn_front = cr_front - sn_l
    model.add_cube("head", "snout", (snap(-sn_w / 2), head_bottom, sn_front), (sn_w, sn_h, sn_l), "snout",
                   tags={"region": REGION_HEAD, "axis": "z"})
    cr_top = head_bottom + cr_h
    sn_top = head_bottom + sn_h

    eye_z = snap(cr_front + min(2.5, max(1.5, cr_l * 0.3)))
    eye_y = snap(cr_top - min(2.5, max(1.5, cr_h * 0.3)))
    for side, face, sign in (("right", "east", 1), ("left", "west", -1)):
        model.add_landmark(Landmark(f"eye_{side}", "head", "skull", face, (sign * cr_w / 2, eye_y, eye_z)))
    for side, sign in (("right", 1), ("left", -1)):
        model.add_landmark(Landmark(
            f"nostril_{side}", "head", "snout", "up", (sign * max(1.0, sn_w / 2 - 1.5), sn_top, sn_front + 1.5)))

    if structure.teeth and features.get("teeth_visible", True):
        tu_w = max(2, sn_w - 2)
        tu_l = sn_l + max(2, cr_l // 3)
        model.add_cube("head", "teeth_upper", (snap(-tu_w / 2), head_bottom - 2, sn_front + 0.5), (tu_w, 3, tu_l),
                       "teeth_upper", material="teeth", tags={"region": REGION_HEAD, "teeth": "upper"})

    if "brows" in extras or features.get("brow_horns"):
        horn = bool(features.get("brow_horns"))
        for side, sign in (("right", 1), ("left", -1)):
            if horn:
                # chifre curto no alto da cabeça, acima do olho
                x0 = cr_w / 2 - 2 if sign > 0 else -cr_w / 2
                frm, size = (snap(x0), cr_top - 1, snap(eye_z - 1.5)), (2, 3, 2)
            else:
                # sobrancelha saliente (1 px para fora) logo acima do olho
                x0 = cr_w / 2 - 1 if sign > 0 else -cr_w / 2 - 1
                frm, size = (snap(x0), eye_y + 1, snap(eye_z - 2)), (2, 1, 4)
            model.add_cube("head", f"brow_{side}", frm, size, "brow",
                           priority=1, tags={"region": REGION_HEAD, "horn": horn})

    if "nasal_ridge" in extras:
        nl = max(2, min(5, sn_l - 2))
        model.add_cube("head", "nasal_ridge", (-1.5, sn_top, sn_front + 1), (3, 1, nl), "nasal_ridge",
                       priority=2, tags={"region": REGION_HEAD})

    if features.get("feather_crest") and "feather_crest" in extras:
        model.add_cube("head", "crest_head", (-0.5, cr_top, snap(Hd[2] - 2)), (1, 2, 4), "crest",
                       material="crest", priority=2, tags={"region": REGION_HEAD})
        model.add_cube("neck", "crest_neck", (-0.5, neck_y0 + neck_h, N[2] - neck_l + 1), (1, 2, max(3, neck_l - 1)),
                       "crest", material="crest", priority=2, tags={"region": REGION_BODY})

    # mandíbula
    J = (0.0, head_bottom, snap(Hd[2] + 1))
    model.add_bone("jaw", J, (jaw_pitch, 0, 0), parent="head")
    jb_l = cr_l - 1
    if structure.jaw_split:
        jb_w = cr_w - 1
        jf_w = sn_w - 1
        model.add_cube("jaw", "jaw_back", (snap(-jb_w / 2), J[1] - jaw_h, J[2] + 1 - jb_l), (jb_w, jaw_h, jb_l), "jaw",
                       tags={"belly": True, "region": REGION_HEAD, "axis": "z"})
        jf_front = J[2] + 1 - jb_l - sn_l
        model.add_cube("jaw", "jaw_front", (snap(-jf_w / 2), J[1] - jaw_h, jf_front), (jf_w, jaw_h, sn_l), "jaw",
                       tags={"belly": True, "region": REGION_HEAD, "axis": "z"})
    else:
        jf_w = cr_w - 2
        jf_front = J[2] + 1 - jb_l - sn_l
        model.add_cube("jaw", "jaw", (snap(-jf_w / 2), J[1] - jaw_h, jf_front), (jf_w, jaw_h, jb_l + sn_l), "jaw",
                       tags={"belly": True, "region": REGION_HEAD, "axis": "z"})
    if structure.teeth and features.get("teeth_visible", True):
        tl_w = max(2, jf_w - 2)
        tl_l = sn_l + max(1, cr_l // 4)
        model.add_cube("jaw", "teeth_lower", (snap(-tl_w / 2), J[1] - 1, jf_front + 0.5), (tl_w, 3, tl_l),
                       "teeth_lower", material="teeth", tags={"region": REGION_HEAD, "teeth": "lower"})

    # braços (pequenos, duas garras por mão)
    for side, sign in (("right", 1), ("left", -1)):
        A = (snap(sign * (tor_w / 2 - 0.5)), snap(tor_y0 + tor_h * 0.35), snap(tor_front + 4))
        arm = f"arm_{side}"
        model.add_bone(arm, A, (arm_pitch, 0, sign * arm_roll), parent="torso")
        ax = A[0] + sign * arm_t / 2
        model.add_cube(arm, "upper_arm", (snap(ax - arm_t / 2), A[1] - ua_len, snap(A[2] - arm_t / 2)),
                       (arm_t, ua_len + 1, arm_t), "upper_arm", tags={"region": REGION_ARMS, "axis": "y"})
        E = (snap(ax), A[1] - ua_len + 0.5, A[2])
        fore = f"forearm_{side}"
        model.add_bone(fore, E, (forearm_pitch, 0, 0), parent=arm)
        model.add_cube(fore, "forearm", (snap(E[0] - arm_t / 2), snap(E[1] - arm_t / 2), E[2] - fa_len),
                       (arm_t, arm_t, fa_len + 1), "forearm", tags={"region": REGION_ARMS, "axis": "z"})
        claw_z = E[2] - fa_len
        claw_y = snap(E[1] - arm_t / 2)
        for k, dx in enumerate((-1.0, 0.0)):
            model.add_cube(fore, f"claw_{k + 1}", (snap(E[0] + dx), claw_y - 2, claw_z), (1, 2, 1), "claw_hand",
                           material="claw", tags={"region": REGION_ARMS})

    # pernas
    leg_x = snap(pel_w / 2 + th_w / 2 - 2)
    for side, sign in (("right", 1), ("left", -1)):
        L = (sign * leg_x, 0.0, 0.0)
        leg = f"leg_{side}"
        model.add_bone(leg, L, (thigh_pitch, 0, 0), parent="body")
        model.add_cube(leg, "thigh", (snap(L[0] - th_w / 2), -(th_len - 3), snap(-th_d / 2 - 0.5)),
                       (th_w, th_len, th_d), "thigh", tags={"region": REGION_LEGS, "axis": "y"})
        K = (L[0], -(th_len - 3) + 1.5, 0.5)
        shin = f"shin_{side}"
        model.add_bone(shin, K, (shin_pitch, 0, 0), parent=leg)
        # sem metatarso a canela termina no tornozelo (senão a quina atravessa o chão)
        shin_extra = 1 if structure.metatarsus else 0
        model.add_cube(shin, "shin", (snap(K[0] - sh_w / 2), K[1] - sh_len + 1 - shin_extra, snap(-sh_d / 2 + 0.5)),
                       (sh_w, sh_len + shin_extra, sh_d), "shin", tags={"region": REGION_LEGS, "axis": "y"})
        An = (K[0], K[1] - sh_len + 1, 0.0)
        parent = shin
        world = thigh_pitch + shin_pitch
        if structure.metatarsus:
            meta = f"metatarsus_{side}"
            model.add_bone(meta, An, (meta_pitch, 0, 0), parent=shin)
            model.add_cube(meta, "metatarsus", (snap(An[0] - mt_w / 2), An[1] - mt_len, snap(-mt_d / 2)),
                           (mt_w, mt_len + 1, mt_d), "metatarsus", tags={"region": REGION_LEGS, "axis": "y"})
            F = (An[0], An[1] - mt_len + 1, 0.0)
            parent = meta
            world += meta_pitch
        else:
            F = An
        foot = f"foot_{side}"
        model.add_bone(foot, F, (-world, 0, 0), parent=parent)
        foot_y0 = F[1] - ft_h + 0.5
        foot_front = snap(-(ft_l - 2.5))
        model.add_cube(foot, "foot", (snap(F[0] - ft_w / 2), foot_y0, foot_front), (ft_w, ft_h, ft_l), "foot",
                       tags={"region": REGION_LEGS, "axis": "z", "toes": 3})
        if "toe_claws" in extras:
            for k, dx in enumerate((-2.0, 0.0, 2.0)):
                cx = F[0] + dx * ft_w / 5.0
                model.add_cube(foot, f"toe_claw_{k + 1}", (snap(cx - 0.5), foot_y0, foot_front - 1.5), (1, 1, 2),
                               "toe_claw", material="claw", priority=2, tags={"region": REGION_LEGS})

    # cauda segmentada
    n = structure.tail_segments
    total = 38.0 * P["tail_length"] * s
    weights = [1.0 - 0.12 * i for i in range(n)]
    lengths = _distribute(total, weights)
    tt = P["tail_thickness"]
    base_w = min(pel_w - 1, I(9 * tt * math.sqrt(bulk), 3))
    base_h = min(pel_h - 2, I(10 * tt, 3))
    tip_w = max(1, I(2 * tt))
    tip_h = max(1, I(2 * tt))
    widths = [int(round(base_w + (tip_w - base_w) * (i / max(1, n - 1)) ** 0.85)) for i in range(n)]
    heights = [int(round(base_h + (tip_h - base_h) * (i / max(1, n - 1)) ** 0.85)) for i in range(n)]
    for i in range(1, n):
        widths[i] = min(widths[i], widths[i - 1])
        heights[i] = min(heights[i], heights[i - 1])
    world_targets = [6.0, 2.0, -1.0, -4.0, -7.0, -9.0][:n]
    tail_cy = snap(pel_top - heights[0] / 2.0 - 0.5)
    parent = "body"
    prev_world = 0.0
    z = pel_back - 1.0
    for i in range(n):
        name = f"tail_{i + 1}"
        world = ang(world_targets[i] + jitter(1.5))
        model.add_bone(name, (0.0, tail_cy, snap(z)), (world - prev_world, 0, 0), parent=parent)
        model.add_cube(name, "tail", (snap(-widths[i] / 2), snap(tail_cy - heights[i] / 2), snap(z)),
                       (widths[i], heights[i], lengths[i] + 1), "tail",
                       tags={"belly": True, "region": REGION_TAIL, "axis": "z", "tail_index": i, "tail_count": n})
        prev_world = world
        parent = name
        z += lengths[i]

    # espinhos dorsais (opcional)
    if features.get("back_spikes") and "back_spikes" in extras:
        sp_h = I(2, 1)
        spots = [
            ("body", 0.0, pel_top, (pel_front + pel_back) / 2),
            ("torso", 0.0, pel_top, tor_front + tor_l * 0.66),
            ("torso", 0.0, pel_top, tor_front + tor_l * 0.33),
            ("neck", 0.0, neck_y0 + neck_h, N[2] - neck_l * 0.5),
        ]
        for i in range(min(2, n)):
            b = model.bones[f"tail_{i + 1}"]
            seg = b.cubes[0]
            spots.append((f"tail_{i + 1}", 0.0, seg.to[1], (seg.frm[2] + seg.to[2]) / 2))
        for k, (bone, x, y, zc) in enumerate(spots):
            model.add_cube(bone, f"spike_{k + 1}", (-0.5, y, snap(zc - 1)), (1, sp_h, 2), "spike", material="spike",
                           priority=2, tags={"region": REGION_BODY})

    _place_on_ground(model)
    _fix_tail_clearance(model, n)
    # registra só os detalhes opcionais que realmente viraram cubos
    parts = {c.part for c in model.iter_cubes()}
    extra_parts = {"brows": "brow", "toe_claws": "toe_claw", "nasal_ridge": "nasal_ridge", "back_spikes": "spike",
                   "feather_crest": "crest"}
    model.meta["extras"] = sorted(e for e in extras if extra_parts.get(e) in parts)
    return model


def _foot_cubes(model: Model):
    return [c for c in model.iter_cubes() if c.part in ("foot", "toe_claw")]


def _place_on_ground(model: Model) -> None:
    """Apoia os pés em Y = 0.

    O deslocamento é arredondado para a grade de 0,5 px para manter as
    coordenadas limpas; os pés ficam a no máximo 0,25 px do chão. O osso
    ``root`` permanece na origem (âncora da criatura no chão).
    """
    lo, _hi = model.world_bounds(_foot_cubes(model))
    model.translate(0.0, snap(-float(lo[1])), 0.0)
    model.bones["root"].pivot = (0.0, 0.0, 0.0)


def _fix_tail_clearance(model: Model, n: int) -> None:
    """Garante que a ponta da cauda não atravesse o chão."""
    for _ in range(20):
        tail_cubes = [c for c in model.iter_cubes() if c.part == "tail"]
        lo, _hi = model.world_bounds(tail_cubes)
        if lo[1] >= 1.0:
            return
        bone = model.bones["tail_1"]
        bone.rotation = (bone.rotation[0] - 2.0, bone.rotation[1], bone.rotation[2])
        if len(model.bones) and "tail_2" in model.bones:
            nxt = model.bones["tail_2"]
            nxt.rotation = (nxt.rotation[0] + 1.0, nxt.rotation[1], nxt.rotation[2])


def count_for(spec: dict[str, Any], settings: BuildSettings, structure: Structure, extras: set[str]) -> int:
    return build_theropod(spec, settings, structure, extras).cube_count


def build_with_budget(spec: dict[str, Any], settings: BuildSettings) -> tuple[Model, list[str]]:
    """Escolhe estrutura e detalhes que caibam no orçamento de elementos."""
    notes: list[str] = []
    detail = spec["detail_level"]
    budget = int(settings.element_budget)
    structure = STRUCTURE_BY_DETAIL[detail]
    extras_allowed = [name for name, _prio, levels in sorted(EXTRAS, key=lambda e: e[1]) if detail in levels]

    # 1) reduz a estrutura até caber (sem extras)
    downgrades = [
        ("tail_segments", lambda st: replace(st, tail_segments=st.tail_segments - 1) if st.tail_segments > 3 else None,
         "cauda com menos segmentos"),
        ("tail_segments", lambda st: replace(st, tail_segments=st.tail_segments - 1) if st.tail_segments > 3 else None,
         "cauda com menos segmentos"),
        ("metatarsus", lambda st: replace(st, metatarsus=False) if st.metatarsus else None, "pés sem metatarso"),
        ("jaw_split", lambda st: replace(st, jaw_split=False) if st.jaw_split else None, "mandíbula em um cubo"),
        ("chest", lambda st: replace(st, chest=False) if st.chest else None, "sem cubo de peito"),
        ("teeth", lambda st: replace(st, teeth=False) if st.teeth else None, "sem dentes em 3D"),
    ]
    count = count_for(spec, settings, structure, set())
    for _key, fn, label in downgrades:
        if count <= budget:
            break
        new = fn(structure)
        if new is None:
            continue
        structure = new
        count = count_for(spec, settings, structure, set())
        notes.append(f"orçamento: {label}")
    if count > budget:
        raise BudgetError(count, budget)

    # 2) acrescenta detalhes opcionais em ordem de prioridade
    extras: set[str] = set()
    for name in extras_allowed:
        trial = extras | {name}
        c = count_for(spec, settings, structure, trial)
        if c <= budget:
            extras = trial
            count = c
        else:
            notes.append(f"orçamento: detalhe '{name}' omitido")
    model = build_theropod(spec, settings, structure, extras)
    return model, notes
