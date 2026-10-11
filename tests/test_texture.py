import numpy as np

from ninho_studio.palette import hex_to_rgb
from ninho_studio.pipeline import generate
from ninho_studio.spec import BuildSettings, default_spec
from ninho_studio.uv import box_uv_face_rects, rect_bounds


def _region(texture, cube, face):
    u0, v0, u1, v1 = (int(x) for x in rect_bounds(box_uv_face_rects(cube.frm, cube.to, cube.uv_offset)[face]))
    return texture[v0:v1, u0:u1]


def _lum(arr):
    rgb = arr[..., :3].astype(float)
    return float((0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).mean())


def test_every_face_region_is_painted_and_rest_transparent(default_result):
    tex = default_result.texture
    used = np.zeros(tex.shape[:2], dtype=bool)
    for cube in default_result.model.iter_cubes():
        for face in ("north", "east", "south", "west", "up", "down"):
            region = _region(tex, cube, face)
            if region.size:
                assert (region[..., 3] == 255).all(), (cube.name, face)
            u0, v0, u1, v1 = (int(x) for x in rect_bounds(box_uv_face_rects(cube.frm, cube.to, cube.uv_offset)[face]))
            used[v0:v1, u0:u1] = True
    assert (tex[~used][..., 3] == 0).all()


def test_belly_is_lighter_than_back(default_result):
    tex = default_result.texture
    for bone, name in (("torso", "torso"), ("body", "pelvis"), ("tail_1", "tail")):
        cube = default_result.model.find_cube(bone, name)
        assert _lum(_region(tex, cube, "down")) > _lum(_region(tex, cube, "up")) + 30, name


def test_eyes_and_mouth_regions(default_result):
    tex = default_result.texture
    spec = default_result.spec
    skull = default_result.model.find_cube("head", "skull")
    eye = np.array(hex_to_rgb(spec["colors"]["eyes"]))
    for face in ("east", "west"):
        region = _region(tex, skull, face)[..., :3].reshape(-1, 3).astype(int)
        assert (np.abs(region - eye).sum(axis=1) < 40).sum() >= 1, face  # íris visível dos dois lados
        assert (region.sum(axis=1) < 60).sum() >= 2, face  # pupila escura
    mouth = np.array(hex_to_rgb(spec["colors"]["mouth"]))
    roof = _region(tex, skull, "down")[..., :3].reshape(-1, 3).astype(int)
    assert np.median(np.abs(roof - mouth).sum(axis=1)) < 80


def test_teeth_have_tooth_and_gum_colors(default_result):
    tex = default_result.texture
    teeth = default_result.model.find_cube("head", "teeth_upper")
    side = _region(tex, teeth, "east")[..., :3].reshape(-1, 3).astype(int)
    claws = np.array(hex_to_rgb(default_result.spec["colors"]["claws"]))
    assert (np.abs(side - claws).sum(axis=1) < 30).sum() >= 2


def test_patterns_differ_and_are_deterministic():
    spec = default_spec()
    outs = {}
    for pattern in ("none", "stripes", "spots", "bands", "mottled"):
        s = default_spec()
        s["pattern"]["type"] = pattern
        outs[pattern] = generate(s, BuildSettings(seed=3), mode="procedural").texture
    for a in outs:
        for b in outs:
            if a < b:
                assert not np.array_equal(outs[a], outs[b]), (a, b)
    again = generate(spec, BuildSettings(seed=3), mode="procedural").texture
    first = generate(spec, BuildSettings(seed=3), mode="procedural").texture
    assert np.array_equal(again, first)


def test_skin_types_and_colors_apply():
    s = default_spec()
    s["colors"]["primary"] = "#3050c0"
    s["pattern"]["type"] = "none"
    tex = generate(s, BuildSettings(seed=1), mode="procedural").texture
    painted = tex[tex[..., 3] == 255][:, :3].astype(int)
    blueish = (painted[:, 2] > painted[:, 0] + 30) & (painted[:, 2] > painted[:, 1])
    assert blueish.mean() > 0.3
    for skin in ("scales", "rough", "smooth", "feathered"):
        s2 = default_spec()
        s2["skin"] = skin
        generate(s2, BuildSettings(seed=1), mode="procedural")
