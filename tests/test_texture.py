import numpy as np

from ninho_studio.palette import hex_to_rgb
from ninho_studio.pipeline import generate
from ninho_studio.texture import CUTOUT_MATERIALS
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
        cutout = cube.material in CUTOUT_MATERIALS
        for face in ("north", "east", "south", "west", "up", "down"):
            region = _region(tex, cube, face)
            if region.size and not cutout:
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


def test_white_creature_stays_white():
    """Teste real do usuário no Colab: T-rex branco saía cinza (rampa escurecia 15% por tom)."""
    from ninho_studio.palette import contrast_ratio, detail_dark, luminance, shade

    white = (255, 255, 255)
    assert luminance(shade(white, -1)) > 0.75 and luminance(shade(white, -2)) > 0.6
    assert contrast_ratio(white, detail_dark(white)) > 4.5  # contorno do olho legível
    s = default_spec()
    s["colors"].update(primary="#ffffff", secondary="#f2f2f2", belly="#fffbe8", pattern="#333333", eyes="#ff6347")
    res = generate(s, BuildSettings(seed=42), mode="procedural")
    torso = res.model.find_cube("torso", "torso")
    for face in ("up", "east", "west"):
        region = _region(res.texture, torso, face)
        rgb = region[..., :3].reshape(-1, 3).astype(int)
        light = (rgb.min(axis=1) > 200).mean()
        assert light > 0.6, (face, light)  # a maior parte continua branca (listras à parte)


def test_green_skin_texture_is_subtle():
    """A microtextura (escamas) muda pouco cada texel: só 40% do caminho até o tom vizinho."""
    def tex(skin):
        sp = default_spec()
        sp["pattern"]["type"] = "none"
        sp["skin"] = skin
        return generate(sp, BuildSettings(seed=42), mode="procedural").texture[..., :3].astype(int)

    smooth, scales = tex("smooth"), tex("scales")
    lum = lambda a: 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]  # noqa: E731
    diff = np.abs(lum(scales) - lum(smooth))
    assert (diff > 0).sum() > 100  # a textura existe
    assert diff.max() < 30  # e é sutil


def test_teeth_are_cut_out_in_zigzag(default_result):
    """Dentes recortados com transparência (o GeckoLib desenha entidades com recorte de alfa)."""
    tex = default_result.texture
    for bone, name in (("head", "teeth_upper"), ("jaw", "teeth_lower")):
        teeth = default_result.model.find_cube(bone, name)
        side = _region(tex, teeth, "east")
        alpha = side[..., 3]
        assert (alpha == 0).any() and (alpha == 255).any(), name
        gum_row = alpha[0] if name == "teeth_upper" else alpha[-1]
        assert (gum_row == 255).all(), name  # junto à gengiva a fileira é contínua
        for face in ("up", "down", "south"):
            assert (_region(tex, teeth, face)[..., 3] == 0).all(), (name, face)


def test_contact_shadow_darkens_corners():
    from ninho_studio.lighting import OcclusionBaker
    from ninho_studio.model import Model

    m = Model("L")
    m.add_bone("root", (0, 0, 0))
    m.add_cube("root", "floor", (0, 0, 0), (12, 1, 12), "pelvis")
    m.add_cube("root", "wall", (0, 1, 0), (1, 8, 12), "pelvis")
    occ = OcclusionBaker(m).occlusion(np.array([[1.5, 1.0, 6.0], [10.5, 1.0, 6.0]]), np.array([0.0, 1.0, 0.0]))
    assert occ[0] > 0.25 and occ[1] < 0.02  # junto da parede escurece; longe dela não


def test_eye_has_slit_pupil_and_glint(default_result):
    tex = default_result.texture
    skull = default_result.model.find_cube("head", "skull")
    eye = np.array(hex_to_rgb(default_result.spec["colors"]["eyes"]))
    for face in ("east", "west"):
        rgb = _region(tex, skull, face)[..., :3].astype(int)
        flat = rgb.reshape(-1, 3)
        assert (flat.sum(axis=1) < 60).sum() == 2  # pupila em fenda: 1 x 2 pixels
        assert (np.abs(flat - eye).sum(axis=1) < 40).sum() >= 2  # íris
        assert (flat.min(axis=1) > 200).sum() >= 1  # brilho
