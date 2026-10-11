"""Construtor procedural de terópodes (base ajustável de T-rex).

O modelo é montado em pose de repouso alinhada aos eixos (como o Blockbench
guarda os cubos) e a postura vem das rotações dos ossos, cada um com o pivô
na articulação correspondente — pronto para animação.

Forma (v0.3): cabeça mais larga atrás (músculos da mandíbula), sobrancelha saliente
sobre o olho, topo arredondado e ponte nasal, dentes de cima por fora da mandíbula
(mordida sobreposta) e língua; pescoço com garganta; placas que arredondam o dorso e o
quadril; coxa robusta e panturrilha; pé com três dedos separados e garras. Esses cubos
pequenos quebram o contorno de caixa, como um artista faria no Blockbench. Faces de
cubos diferentes que ficam no mesmo plano recebem uma fração de pixel de ``inflate``
(ver :mod:`ninho_studio.coplanar`).

Hierarquia::

    root
    └── body (hip/pelvis)
        ├── torso
        │   ├── neck
        │   │   └── head
        │   │       └── jaw
        │   ├── arm_right ── forearm_right
        │   └── arm_left ─── forearm_left
        ├── tail_1 ── tail_2 ── ... (4 a 6 segmentos)
        ├── leg_right ── shin_right ── [metatarsus_right] ── foot_right
        └── leg_left ─── shin_left ─── [metatarsus_left] ─── foot_left
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Any, Optional

from ..coplanar import resolve_model
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
    toes: bool = True  # dedos separados (senão, pé inteiriço com dedos pintados)
    rounding: bool = True  # placas que arredondam dorso, quadril, topo da cabeça e focinho
    cheeks: bool = True  # músculos da mandíbula (cabeça mais larga atrás)
    muscles: bool = True  # panturrilha
    throat: bool = True  # garganta sob o pescoço
    tongue: bool = True


STRUCTURE_BY_DETAIL = {
    "low": Structure(tail_segments=4, metatarsus=True, jaw_split=False, chest=False, teeth=True, toes=False,
                     rounding=False, cheeks=True, muscles=False, throat=False, tongue=False),
    "medium": Structure(tail_segments=5, metatarsus=True, jaw_split=True, chest=True, teeth=True),
    "high": Structure(tail_segments=6, metatarsus=True, jaw_split=True, chest=True, teeth=True),
}

# Detalhes opcionais: (nome, prioridade, níveis de detalhe que o permitem)
EXTRAS = [
    ("brows", 1, ("medium", "high")),
    ("toe_claws", 1, ("medium", "high")),
    ("nasal_ridge", 2, ("high",)),
    ("dewclaws", 2, ("high",)),
    ("back_scutes", 3, ("high",)),
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
    return [max(2, int(round(r))) for r in raw]


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
    pel_w, pel_h, pel_l = I(11 * bulk, 4), I(13 * bulk, 4), I(9 * blen, 4)
    tor_w, tor_h, tor_l = I(13 * bulk, 4), I(16 * bulk, 4), I(13 * blen, 4)
    neck_factor = 0.6 * bulk + 0.4 * hs
    neck_w, neck_h, neck_l = I(9 * neck_factor, 3), I(10 * neck_factor, 3), I(8 * P["neck_length"], 3)
    cr_w, cr_h, cr_l = I(11 * hs, 4), I(9 * hs, 4), I(11 * hs, 4)
    sn_w = min(I(9 * hs, 3), cr_w - 2)
    sn_h = min(I(6 * hs, 3), cr_h - 2)
    sn_l = I(9 * hs * P["snout_length"], 3)
    jaw_hb = I(4 * hs, 2)  # fundo da mandíbula (mais alto)
    jaw_hf = max(2, min(jaw_hb - 1, I(3 * hs, 2)))  # frente da mandíbula
    tooth_h = I(3 * hs, 2)

    al = P["arm_length"]
    arm_t = I(2 * (0.75 + 0.25 * bulk), 1)
    ua_len = I(4 * al, 2)
    fa_len = I(4 * al, 2)

    ll, lt = P["leg_length"], P["leg_thickness"]
    th_w, th_len, th_d = I(7 * lt * (0.85 + 0.15 * bulk), 3), I(14 * ll, 6), I(10 * lt, 4)
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
    if structure.rounding and pel_w > 4:
        model.add_cube("body", "hip_top", (snap(-(pel_w - 2) / 2), pel_top, pel_front + 1), (pel_w - 2, 1, pel_l - 2),
                       "hip_top", priority=1, tags={"region": REGION_BODY, "dorsal": True})

    # tronco
    T = (0.0, snap(pel_top - 5), snap(pel_front + 1))
    model.add_bone("torso", T, (torso_pitch, 0, 0), parent="body")
    tor_y0 = pel_top - tor_h
    tor_z0 = T[2] - tor_l
    model.add_cube("torso", "torso", (snap(-tor_w / 2), tor_y0, tor_z0), (tor_w, tor_h, tor_l + 2), "torso",
                   tags={"belly": True, "region": REGION_BODY, "axis": "z"})
    tor_front = tor_z0
    if structure.rounding and tor_w > 4:
        model.add_cube("torso", "torso_back", (snap(-(tor_w - 2) / 2), pel_top, tor_z0 + 1), (tor_w - 2, 1, tor_l),
                       "torso_back", priority=1, tags={"region": REGION_BODY, "dorsal": True})
    if structure.chest:
        ch_w = max(3, tor_w - 3)
        ch_l = max(4, int(round(tor_l * 0.6)))
        frm, size = _box(0, tor_y0 - 1.5, tor_front + 2 + ch_l / 2, ch_w, 5, ch_l)
        model.add_cube("torso", "chest", frm, size, "chest", tags={"belly": True, "region": REGION_BODY, "axis": "z"})

    # pescoço
    N = (0.0, snap(pel_top - 3), snap(tor_front + 2.5))
    model.add_bone("neck", N, (neck_pitch, 0, 0), parent="torso")
    neck_y0 = snap(N[1] - neck_h * 0.6)
    model.add_cube("neck", "neck", (snap(-neck_w / 2), neck_y0, N[2] - neck_l), (neck_w, neck_h, neck_l + 2), "neck",
                   tags={"belly": True, "region": REGION_BODY, "axis": "z"})
    if structure.throat and neck_w > 4:
        model.add_cube("neck", "throat", (snap(-(neck_w - 2) / 2), neck_y0 - 2, N[2] - neck_l + 1),
                       (neck_w - 2, 2, max(2, neck_l - 1)), "throat", priority=1,
                       tags={"belly": True, "region": REGION_BODY, "axis": "z"})

    # cabeça
    Hd = (0.0, snap(N[1] + 0.5), snap(N[2] - neck_l + 1.5))
    model.add_bone("head", Hd, (head_pitch, 0, 0), parent="neck")
    head_bottom = Hd[1] - 2.5
    cr_front = Hd[2] - (cr_l - 2)
    cr_back = cr_front + cr_l
    model.add_cube("head", "skull", (snap(-cr_w / 2), head_bottom, cr_front), (cr_w, cr_h, cr_l), "skull",
                   tags={"region": REGION_HEAD, "axis": "z"})
    cr_top = head_bottom + cr_h
    sn_front = cr_front - sn_l
    model.add_cube("head", "snout", (snap(-sn_w / 2), head_bottom, sn_front), (sn_w, sn_h, sn_l), "snout",
                   tags={"region": REGION_HEAD, "axis": "z"})
    sn_top = head_bottom + sn_h
    if structure.rounding:
        if cr_w > 4 and cr_l > 4:
            model.add_cube("head", "skull_top", (snap(-(cr_w - 2) / 2), cr_top, cr_front + 1),
                           (cr_w - 2, 1, cr_l - 3), "skull_top", priority=1, tags={"region": REGION_HEAD, "dorsal": True})
        if sn_w > 3 and sn_l > 2:
            model.add_cube("head", "snout_top", (snap(-(sn_w - 2) / 2), sn_top, sn_front + 1),
                           (sn_w - 2, 1, sn_l - 1), "snout_top", priority=1, tags={"region": REGION_HEAD, "dorsal": True})
    if structure.cheeks:
        ch_h = max(2, min(cr_h - 2, I(4 * hs, 2)))
        ch_l = max(3, min(cr_l - 2, I(5 * hs, 3)))
        for side, sign in (("right", 1), ("left", -1)):
            x0 = cr_w / 2 if sign > 0 else -cr_w / 2 - 1
            model.add_cube("head", f"cheek_{side}", (snap(x0), head_bottom, cr_back - ch_l), (1, ch_h, ch_l), "cheek",
                           priority=1, tags={"region": REGION_HEAD, "side": sign})

    # olhos no alto do crânio, logo abaixo da sobrancelha
    eye_y = cr_top - 2 if cr_h >= 5 else cr_top - 1.5
    eye_z = cr_front + (2.5 if cr_l < 13 else 3.5)
    for side, face, sign in (("right", "east", 1), ("left", "west", -1)):
        model.add_landmark(Landmark(f"eye_{side}", "head", "skull", face, (sign * cr_w / 2, eye_y, eye_z)))
    # narinas no alto da ponta do focinho
    nostril_cube = "snout_top" if structure.rounding and sn_w > 3 and sn_l > 2 else "snout"
    nostril_x = max(0.5, (sn_w - 2) / 2 - 1.0) if nostril_cube == "snout_top" else max(1.0, sn_w / 2 - 1.5)
    nostril_y = sn_top + (1 if nostril_cube == "snout_top" else 0)
    nostril_z = sn_front + (1.5 if nostril_cube == "snout_top" else 1.5)
    for side, sign in (("right", 1), ("left", -1)):
        model.add_landmark(Landmark(f"nostril_{side}", "head", nostril_cube, "up",
                                    (sign * nostril_x, nostril_y, nostril_z)))

    teeth = structure.teeth and features.get("teeth_visible", True)
    if teeth:
        # dentes de cima por fora da mandíbula (mordida sobreposta): aparecem mesmo de boca fechada
        tu_w = max(2, sn_w - 1)
        model.add_cube("head", "teeth_upper", (snap(-tu_w / 2), head_bottom - tooth_h, sn_front + 0.5),
                       (tu_w, tooth_h, sn_l + 1), "teeth_upper", material="teeth",
                       tags={"region": REGION_HEAD, "teeth": "upper"})

    if "brows" in extras or features.get("brow_horns"):
        horn = bool(features.get("brow_horns"))
        for side, sign in (("right", 1), ("left", -1)):
            x0 = cr_w / 2 - 1 if sign > 0 else -cr_w / 2 - 1
            if horn:
                # chifre curto acima do olho, saindo do alto da cabeça
                frm, size = (snap(x0), cr_top - 1, snap(eye_z - 1.5)), (2, 4, 2)
            else:
                # sobrancelha saliente: 1 px para o lado e 1 px acima do crânio, sobre o olho
                frm, size = (snap(x0), eye_y + 1, snap(eye_z - 2)), (2, int(round(cr_top + 1 - (eye_y + 1))), 4)
            model.add_cube("head", f"brow_{side}", frm, size, "brow",
                           priority=1, tags={"region": REGION_HEAD, "horn": horn, "side": sign})

    if "nasal_ridge" in extras:
        top = sn_top + (1 if nostril_cube == "snout_top" else 0)
        nl = max(2, min(4, sn_l - 3))
        model.add_cube("head", "nasal_ridge", (-1.0, top, sn_front + 3), (2, 1, nl), "nasal_ridge",
                       priority=2, tags={"region": REGION_HEAD})

    if features.get("feather_crest") and "feather_crest" in extras:
        crest_base = cr_top + (1 if structure.rounding else 0)
        model.add_cube("head", "crest_head", (-0.5, crest_base, snap(Hd[2] - 2)), (1, 2, 4), "crest",
                       material="crest", priority=2, tags={"region": REGION_HEAD})
        model.add_cube("neck", "crest_neck", (-0.5, neck_y0 + neck_h, N[2] - neck_l + 1), (1, 2, max(3, neck_l - 1)),
                       "crest", material="crest", priority=2, tags={"region": REGION_BODY})

    # mandíbula (dobradiça no fundo do crânio)
    J = (0.0, head_bottom, snap(Hd[2] + 1))
    model.add_bone("jaw", J, (jaw_pitch, 0, 0), parent="head")
    jb_l = cr_l - 1
    if structure.jaw_split:
        jb_w = max(3, cr_w - 2)
        jf_w = max(2, min(jb_w - 2, sn_w - 2))
        model.add_cube("jaw", "jaw_back", (snap(-jb_w / 2), J[1] - jaw_hb, J[2] + 1 - jb_l), (jb_w, jaw_hb, jb_l), "jaw",
                       tags={"belly": True, "region": REGION_HEAD, "axis": "z"})
        jf_front = J[2] + 1 - jb_l - sn_l
        model.add_cube("jaw", "jaw_front", (snap(-jf_w / 2), J[1] - jaw_hf, jf_front), (jf_w, jaw_hf, sn_l), "jaw",
                       tags={"belly": True, "region": REGION_HEAD, "axis": "z"})
    else:
        jf_w = max(2, sn_w - 2)
        jf_front = J[2] + 1 - jb_l - sn_l
        model.add_cube("jaw", "jaw", (snap(-jf_w / 2), J[1] - jaw_hb, jf_front), (jf_w, jaw_hb, jb_l + sn_l), "jaw",
                       tags={"belly": True, "region": REGION_HEAD, "axis": "z"})
    if teeth:
        tl_w = max(2, jf_w - 1)
        model.add_cube("jaw", "teeth_lower", (snap(-tl_w / 2), J[1], jf_front + 0.5), (tl_w, tooth_h, sn_l),
                       "teeth_lower", material="teeth", tags={"region": REGION_HEAD, "teeth": "lower"})
    if structure.tongue and jf_w > 3:
        tg_w = max(2, jf_w - 2)
        model.add_cube("jaw", "tongue", (snap(-tg_w / 2), J[1], jf_front + 1.5), (tg_w, 1, sn_l + max(2, jb_l // 2)),
                       "tongue", material="tongue", priority=1, tags={"region": REGION_HEAD})

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
    toe_m = max(3, I(6 * (0.6 + 0.4 * lt), 3))  # dedo do meio
    toe_s = max(2, toe_m - 2)  # dedos dos lados
    toe_w = 2 if ft_w >= 5 else 1
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
        if structure.muscles and sh_w > 2:
            calf_h = max(3, int(round(sh_len * 0.5)))
            model.add_cube(shin, "calf", (snap(K[0] - (sh_w - 1) / 2), K[1] - calf_h + 0.5, snap(sh_d / 2 - 0.5)),
                           (sh_w - 1, calf_h, 2), "calf", priority=1, tags={"region": REGION_LEGS, "axis": "y"})
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
            if "dewclaws" in extras:
                dx = -mt_w / 2 - 1 if sign > 0 else mt_w / 2  # do lado de dentro da perna
                model.add_cube(meta, "dewclaw", (snap(An[0] + dx), F[1] + 1, snap(mt_d / 2 - 0.5)), (1, 1, 2),
                               "dewclaw", material="claw", priority=2, tags={"region": REGION_LEGS})
        else:
            F = An
        foot = f"foot_{side}"
        model.add_bone(foot, F, (-world, 0, 0), parent=parent)
        foot_y0 = F[1] - ft_h + 0.5
        if structure.toes:
            heel_w = max(2, ft_w - 2)
            model.add_cube(foot, "heel", (snap(F[0] - heel_w / 2), foot_y0, -1.5), (heel_w, ft_h, 4), "foot",
                           tags={"region": REGION_LEGS, "axis": "z", "heel": True})
            spread = (ft_w - toe_w) / 2
            for k, (dx, length, yaw) in enumerate(((-spread, toe_s, 12.5), (0.0, toe_m, 0.0), (spread, toe_s, -12.5))):
                cx = F[0] + dx
                base_z = -0.5
                toe_front = base_z - length
                origin = (snap(cx), foot_y0, base_z)
                rot = (0.0, yaw, 0.0)
                cube = model.add_cube(foot, f"toe_{k + 1}", (snap(cx - toe_w / 2), foot_y0, toe_front),
                                      (toe_w, ft_h, length), "toe", origin=origin,
                                      tags={"region": REGION_LEGS, "axis": "z", "toe": k})
                cube.rotation = rot
                if "toe_claws" in extras:
                    claw = model.add_cube(foot, f"toe_claw_{k + 1}", (snap(cx - 0.5), foot_y0, toe_front - 1.5),
                                          (1, 1, 2), "toe_claw", material="claw", priority=1, origin=origin,
                                          tags={"region": REGION_LEGS})
                    claw.rotation = rot
        else:
            foot_front = snap(-(ft_l - 2.5))
            model.add_cube(foot, "foot", (snap(F[0] - ft_w / 2), foot_y0, foot_front), (ft_w, ft_h, ft_l), "foot",
                           tags={"region": REGION_LEGS, "axis": "z", "toes": 3})
            if "toe_claws" in extras:
                for k, dx in enumerate((-2.0, 0.0, 2.0)):
                    cx = F[0] + dx * ft_w / 5.0
                    model.add_cube(foot, f"toe_claw_{k + 1}", (snap(cx - 0.5), foot_y0, foot_front - 1.5), (1, 1, 2),
                                   "toe_claw", material="claw", priority=1, tags={"region": REGION_LEGS})

    # cauda segmentada
    n = structure.tail_segments
    total = 34.0 * P["tail_length"] * s
    weights = [1.0 - 0.1 * i for i in range(n)]
    lengths = _distribute(total, weights)
    tt = P["tail_thickness"]
    base_w = min(pel_w - 1, I(9 * tt * math.sqrt(bulk), 3))
    base_h = min(pel_h - 2, I(10 * tt, 3))
    tip_w = max(1, I(2 * tt))
    tip_h = max(1, I(2 * tt))
    widths = [int(round(base_w + (tip_w - base_w) * (i / max(1, n - 1)) ** 1.15)) for i in range(n)]
    heights = [int(round(base_h + (tip_h - base_h) * (i / max(1, n - 1)) ** 1.15)) for i in range(n)]
    for i in range(1, n):
        widths[i] = min(widths[i], widths[i - 1])
        heights[i] = min(heights[i], heights[i - 1])
    world_targets = [6.0, 3.0, 0.0, -2.5, -5.0, -7.0][:n]
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

    # plaquinhas dorsais (osteodermos) no dorso e no começo da cauda
    if "back_scutes" in extras and not features.get("back_spikes"):
        spots = [("torso", pel_top + (1 if structure.rounding else 0), tor_front + tor_l * 0.5),
                 ("body", pel_top + (1 if structure.rounding else 0), (pel_front + pel_back) / 2)]
        for i in range(min(3, n)):
            seg = model.bones[f"tail_{i + 1}"].cubes[0]
            spots.append((f"tail_{i + 1}", seg.to[1], (seg.frm[2] + seg.to[2]) / 2))
        for k, (bone, y, zc) in enumerate(spots):
            model.add_cube(bone, f"scute_{k + 1}", (-1.0, y, snap(zc - 1)), (2, 1, 2), "scute",
                           priority=3, tags={"region": REGION_BODY})

    # espinhos dorsais (opcional)
    if features.get("back_spikes") and "back_spikes" in extras:
        sp_h = I(2, 1)
        lift = 1 if structure.rounding else 0
        spots = [
            ("body", 0.0, pel_top + lift, (pel_front + pel_back) / 2),
            ("torso", 0.0, pel_top + lift, tor_front + tor_l * 0.66),
            ("torso", 0.0, pel_top + lift, tor_front + tor_l * 0.33),
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
    model.meta["coplanar_fixes"] = resolve_model(model)
    # registra só os detalhes opcionais que realmente viraram cubos
    parts = {c.part for c in model.iter_cubes()}
    extra_parts = {"brows": "brow", "toe_claws": "toe_claw", "nasal_ridge": "nasal_ridge", "back_spikes": "spike",
                   "feather_crest": "crest", "dewclaws": "dewclaw", "back_scutes": "scute"}
    model.meta["extras"] = sorted(e for e in extras if extra_parts.get(e) in parts)
    return model


GROUND_PARTS = ("foot", "toe", "toe_claw")


def _foot_cubes(model: Model):
    return [c for c in model.iter_cubes() if c.part in GROUND_PARTS]


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


# Simplificações aplicadas nesta ordem quando o orçamento não basta (as menos visíveis primeiro)
DOWNGRADES = [
    ("tongue", "sem língua"),
    ("throat", "sem garganta"),
    ("muscles", "sem panturrilha"),
    ("rounding", "sem placas de arredondamento"),
    ("tail_segments", "cauda com menos segmentos"),
    ("cheeks", "sem bochechas"),
    ("toes", "pé inteiriço (dedos pintados)"),
    ("tail_segments", "cauda com menos segmentos"),
    ("metatarsus", "pés sem metatarso"),
    ("jaw_split", "mandíbula em um cubo"),
    ("chest", "sem cubo de peito"),
    ("teeth", "sem dentes em 3D"),
]


def _downgrade(structure: Structure, key: str) -> Optional[Structure]:
    if key == "tail_segments":
        return replace(structure, tail_segments=structure.tail_segments - 1) if structure.tail_segments > 3 else None
    if getattr(structure, key):
        return replace(structure, **{key: False})
    return None


def build_with_budget(spec: dict[str, Any], settings: BuildSettings) -> tuple[Model, list[str]]:
    """Escolhe estrutura e detalhes que caibam no orçamento de elementos."""
    notes: list[str] = []
    detail = spec["detail_level"]
    budget = int(settings.element_budget)
    structure = STRUCTURE_BY_DETAIL[detail]
    extras_allowed = [name for name, _prio, levels in sorted(EXTRAS, key=lambda e: e[1]) if detail in levels]

    # 1) simplifica a estrutura até caber (sem extras)
    count = count_for(spec, settings, structure, set())
    for key, label in DOWNGRADES:
        if count <= budget:
            break
        new = _downgrade(structure, key)
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
