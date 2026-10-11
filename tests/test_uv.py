import numpy as np
import pytest

from ninho_studio.uv import FACE_NORMALS, FACES, PackItem, box_uv_face_rects, box_uv_footprint, pack, uv_to_local

# Valores gravados pelo próprio Blockbench 5.2.2 (projeto de referência gerado na
# build web oficial; ver docs/FORMATO-BBMODEL.md).
BLOCKBENCH_REFERENCE = [
    (
        {"from": [-4, 8, -6], "to": [4, 16, 6], "uv_offset": [0, 0]},
        {"north": [12, 12, 20, 20], "east": [0, 12, 12, 20], "south": [32, 12, 40, 20],
         "west": [20, 12, 32, 20], "up": [20, 12, 12, 0], "down": [28, 0, 20, 12]},
    ),
    (
        {"from": [-3, 14, -12], "to": [3, 20, -6], "uv_offset": [0, 20]},
        {"north": [6, 26, 12, 32], "east": [0, 26, 6, 32], "south": [18, 26, 24, 32],
         "west": [12, 26, 18, 32], "up": [12, 26, 6, 20], "down": [18, 20, 12, 26]},
    ),
]


@pytest.mark.parametrize("cube, expected", BLOCKBENCH_REFERENCE)
def test_box_uv_matches_blockbench(cube, expected):
    assert box_uv_face_rects(cube["from"], cube["to"], cube["uv_offset"]) == expected


def test_footprint():
    assert box_uv_footprint((8, 8, 12)) == (40, 20)
    assert box_uv_footprint((3, 0, 2)) == (10, 2)


def test_mirror_uv_swaps_east_west():
    normal = box_uv_face_rects([0, 0, 0], [4, 4, 2], [0, 0])
    mirrored = box_uv_face_rects([0, 0, 0], [4, 4, 2], [0, 0], mirror_uv=True)
    assert sorted(normal["east"]) == sorted(mirrored["west"])
    assert mirrored["north"] == [normal["north"][2], normal["north"][1], normal["north"][0], normal["north"][3]]


@pytest.mark.parametrize("face", FACES)
def test_uv_to_local_lies_on_face(face):
    frm, to = [1, 2, 3], [5, 8, 7]
    uv = box_uv_face_rects(frm, to, [0, 0])[face]
    cu, cv = (uv[0] + uv[2]) / 2, (uv[1] + uv[3]) / 2
    p = uv_to_local(face, uv, frm, to, cu, cv)
    center = (np.array(frm) + np.array(to)) / 2
    n = np.array(FACE_NORMALS[face])
    half = (np.array(to) - np.array(frm)) / 2
    # o ponto fica no plano da face e no centro dela
    assert np.allclose(p, center + n * half)


def test_uv_to_local_orientation_side_faces():
    frm, to = [0, 0, 0], [4, 6, 2]
    uv = box_uv_face_rects(frm, to, [0, 0])
    # topo da textura = topo do cubo nas faces laterais
    for face in ("north", "south", "east", "west"):
        top = uv_to_local(face, uv[face], frm, to, (uv[face][0] + uv[face][2]) / 2, min(uv[face][1], uv[face][3]))
        assert top[1] == pytest.approx(to[1])
    # face leste (+X) vista de fora: esquerda = sul (+Z)
    left = uv_to_local("east", uv["east"], frm, to, uv["east"][0], uv["east"][1])
    assert left[2] == pytest.approx(to[2])


def test_pack_no_overlap_and_in_bounds():
    items = [PackItem(k, w, h) for k, (w, h) in enumerate([(40, 20), (30, 30), (12, 6), (60, 10), (8, 8)] * 3)]
    placed = pack(items, 128, 128)
    assert placed is not None
    grid = np.zeros((128, 128), dtype=int)
    for it in items:
        x, y = placed[it.key]
        assert 0 <= x and x + it.width <= 128 and 0 <= y and y + it.height <= 128
        grid[y:y + it.height, x:x + it.width] += 1
    assert grid.max() == 1


def test_pack_returns_none_when_too_big():
    assert pack([PackItem(0, 200, 10)], 128, 128) is None


def test_shape_packing_uses_empty_corners():
    from ninho_studio.uv import box_uv_shape, pack_shapes

    big = PackItem("big", *box_uv_footprint((10, 4, 10)), rects=box_uv_shape((10, 4, 10)))  # 40 x 14, cantos 10x10 vazios
    small = PackItem("small", *box_uv_footprint((2, 6, 2)), rects=box_uv_shape((2, 6, 2)))  # 8 x 8
    placed = pack_shapes([big, small], 40, 14, "height")
    assert placed is not None  # só cabe usando um canto vazio do cubo grande
    assert pack([big, small], 40, 14) is None  # o empacotador por retângulos não consegue
    grid = np.zeros((14, 40), dtype=int)
    for it in (big, small):
        x, y = placed[it.key]
        for x0, y0, x1, y1 in it.occupied():
            grid[y + y0:y + y1, x + x0:x + x1] += 1
    assert grid.max() == 1


def test_atlas_size_default_and_big_head():
    """O T-rex padrão cabe em 128x128; com a cabeça 1.4x (mais área de pele) sobe para 256, sem sobreposição."""
    from ninho_studio.pipeline import generate
    from ninho_studio.spec import BuildSettings, default_spec

    res = generate(default_spec(), BuildSettings(seed=42, texture_size=128), mode="procedural")
    assert res.atlas.size == 128 and not res.atlas.upgraded
    spec = default_spec()
    spec["proportions"]["head_size"] = 1.4
    res = generate(spec, BuildSettings(seed=42, texture_size=128), mode="procedural")
    assert res.atlas.size == 256 and res.atlas.upgraded
    assert res.validation.ok and not res.validation.warnings
