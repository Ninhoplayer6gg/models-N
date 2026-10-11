import numpy as np
import pytest

from ninho_studio.builders import BudgetError, build_model
from ninho_studio.spec import BuildSettings, default_spec

REQUIRED_BONES = {
    "root": None, "body": "root", "torso": "body", "neck": "torso", "head": "neck", "jaw": "head",
    "arm_right": "torso", "arm_left": "torso", "forearm_right": "arm_right", "forearm_left": "arm_left",
    "leg_right": "body", "leg_left": "body", "shin_right": "leg_right", "shin_left": "leg_left",
    "tail_1": "body",
}


def build(**changes):
    spec = default_spec()
    settings = BuildSettings(seed=changes.pop("seed", 42), element_budget=changes.pop("budget", 96))
    for key, value in changes.items():
        if key in spec["proportions"]:
            spec["proportions"][key] = value
        else:
            spec[key] = value
    model, notes = build_model(spec, settings)
    return model, notes


def test_hierarchy_and_names():
    model, _ = build()
    for bone, parent in REQUIRED_BONES.items():
        assert bone in model.bones, bone
        assert model.bones[bone].parent == parent, bone
    assert len({b.name for b in model.bones.values()}) == len(model.bones)


@pytest.mark.parametrize("detail, segments", [("low", 4), ("medium", 5), ("high", 6)])
def test_tail_segments_taper(detail, segments):
    model, _ = build(detail_level=detail)
    tails = [model.bones[f"tail_{i + 1}"].cubes[0] for i in range(segments)]
    assert f"tail_{segments + 1}" not in model.bones
    widths = [c.size[0] for c in tails]
    heights = [c.size[1] for c in tails]
    assert widths == sorted(widths, reverse=True) and widths[0] > widths[-1]
    assert heights == sorted(heights, reverse=True) and heights[0] > heights[-1]
    for i in range(1, segments):  # cada segmento é filho do anterior
        assert model.bones[f"tail_{i + 1}"].parent == f"tail_{i}"


def test_two_claws_per_hand_and_jaw():
    model, _ = build()
    for side in ("right", "left"):
        claws = [c for c in model.bones[f"forearm_{side}"].cubes if c.part == "claw_hand"]
        assert len(claws) == 2
    jaw = model.bones["jaw"]
    head = model.bones["head"]
    assert jaw.rotation[0] < 0  # boca entreaberta por padrão
    skull = model.find_cube("head", "skull")
    # dobradiça na parte de trás/baixo do crânio
    assert abs(jaw.pivot[1] - skull.frm[1]) < 1e-6
    assert skull.to[2] - 3 <= jaw.pivot[2] <= skull.to[2]
    assert jaw.parent == head.name


def test_feet_on_ground_and_nothing_below():
    for detail in ("low", "medium", "high"):
        model, _ = build(detail_level=detail)
        feet = [c for c in model.iter_cubes() if c.part == "foot"]
        lo, _hi = model.world_bounds(feet)
        assert abs(lo[1]) <= 0.25, detail
        lo_all, _ = model.world_bounds()
        assert lo_all[1] >= -0.3, detail
        for side in ("right", "left"):
            # pé paralelo ao chão: soma das rotações da perna = 0
            total = sum(b.rotation[0] for b in model.chain(f"foot_{side}"))
            assert total == pytest.approx(0.0)


def test_grid_alignment():
    model, _ = build()
    for bone in model.bones.values():
        for v in bone.pivot:
            assert abs(v * 2 - round(v * 2)) < 1e-9
        for r in bone.rotation:
            assert abs(r * 2 - round(r * 2)) < 1e-9
        for c in bone.cubes:
            for v in c.frm + c.to:
                assert abs(v * 2 - round(v * 2)) < 1e-9
            for s in c.size:
                assert abs(s - round(s)) < 1e-9 and s >= 0


def test_proportions_change_geometry():
    base, _ = build()
    big_head, _ = build(head_size=1.5)
    assert big_head.find_cube("head", "skull").size[0] > base.find_cube("head", "skull").size[0]
    long_tail, _ = build(tail_length=1.5)

    def tail_len(m):
        cubes = [c for c in m.iter_cubes() if c.part == "tail"]
        return sum(c.size[2] for c in cubes)

    assert tail_len(long_tail) > tail_len(base)
    long_legs, _ = build(leg_length=1.4)
    assert long_legs.world_pivot("body")[1] > base.world_pivot("body")[1]


def test_budget_reduces_structure_and_errors():
    model, notes = build(detail_level="high", budget=30)
    assert model.cube_count <= 30
    assert notes
    with pytest.raises(BudgetError):
        build(budget=16)


def test_determinism_and_seed_variation():
    a, _ = build(seed=5)
    b, _ = build(seed=5)
    c, _ = build(seed=6)
    rot = lambda m: [bone.rotation for bone in m.bones.values()]  # noqa: E731
    assert rot(a) == rot(b)
    assert rot(a) != rot(c)


def test_features_add_parts():
    spec_changes = {"features": {**default_spec()["features"], "back_spikes": True, "feather_crest": True,
                                 "brow_horns": True}}
    model, _ = build(**spec_changes)
    parts = {c.part for c in model.iter_cubes()}
    assert {"spike", "crest", "brow"} <= parts
    plain, _ = build(features={**default_spec()["features"], "teeth_visible": False})
    assert "teeth_upper" not in {c.part for c in plain.iter_cubes()}


def test_world_matrix_matches_manual_chain():
    model, _ = build()
    from ninho_studio.geometry import pivot_matrix

    m = np.eye(4)
    for name in ("root", "body", "torso", "neck", "head"):
        b = model.bones[name]
        m = m @ pivot_matrix(b.pivot, b.rotation)
    assert np.allclose(m, model.world_matrix("head"))


def test_feet_have_three_separate_toes_with_claws():
    model, _ = build()
    for side in ("right", "left"):
        cubes = model.bones[f"foot_{side}"].cubes
        toes = [c for c in cubes if c.part == "toe"]
        claws = [c for c in cubes if c.part == "toe_claw"]
        assert len(toes) == 3 and len(claws) == 3
        yaws = sorted(c.rotation[1] for c in toes)
        assert yaws[0] == -yaws[2] < 0 and yaws[1] == 0  # dedos dos lados abertos em leque, simétricos
        for claw in claws:  # cada garra gira junto com o seu dedo
            assert any(claw.origin == t.origin and claw.rotation == t.rotation for t in toes)
    low, _ = build(detail_level="low")
    assert not [c for c in low.iter_cubes() if c.part == "toe"]  # detalhe baixo: pé inteiriço


def test_head_details_overbite_brows_cheeks_tongue():
    model, _ = build()
    head = model.bones["head"]
    skull = model.find_cube("head", "skull")
    teeth_up = model.find_cube("head", "teeth_upper")
    jaw_front = model.find_cube("jaw", "jaw_front")
    # dentes de cima por fora da mandíbula: aparecem mesmo de boca fechada
    assert teeth_up.size[0] > jaw_front.size[0]
    assert teeth_up.frm[0] < jaw_front.frm[0] and jaw_front.to[0] < teeth_up.to[0]
    brows = [c for c in head.cubes if c.part == "brow"]
    assert len(brows) == 2 and all(c.to[1] == skull.to[1] + 1 for c in brows)  # saliente acima do crânio
    assert len([c for c in head.cubes if c.part == "cheek"]) == 2  # cabeça mais larga atrás
    tongue = model.find_cube("jaw", "tongue")
    assert jaw_front.frm[0] < tongue.frm[0] and tongue.to[0] < jaw_front.to[0]


def test_high_detail_with_all_features_fits_default_budget():
    feats = {**default_spec()["features"], "back_spikes": True, "feather_crest": True, "brow_horns": True}
    spec = default_spec()
    spec["detail_level"] = "high"
    spec["features"] = feats
    model, notes = build_model(spec, BuildSettings(seed=4))
    assert not notes
    assert model.cube_count <= BuildSettings().element_budget
    assert {"spike", "crest", "brow", "toe", "toe_claw", "dewclaw", "calf"} <= {c.part for c in model.iter_cubes()}
