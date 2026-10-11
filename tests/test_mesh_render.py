import numpy as np

from ninho_studio.mesh import build_mesh
from ninho_studio.render import VIEWS, atlas_debug, contact_sheet, render, skeleton_sheet
from ninho_studio.viewer import viewer_html


def test_mesh_counts_and_bones(default_result):
    mesh = build_mesh(default_result.bbmodel)
    faces_with_area = 0
    for cube in default_result.model.iter_cubes():
        w, h, d = cube.size
        faces_with_area += 2 * ((w * h > 0) + (w * d > 0) + (h * d > 0))
    assert len(mesh.positions) == 2 * faces_with_area
    assert set(mesh.bones) == set(default_result.model.bones)
    for name, bone in mesh.bones.items():
        assert np.allclose(bone.pivot_world, default_result.model.world_pivot(name))


def test_mesh_bounds_match_model(default_result):
    mesh = build_mesh(default_result.bbmodel)
    lo, hi = mesh.bounds
    mlo, mhi = default_result.model.world_bounds(inflated=True)
    assert np.allclose(lo, mlo) and np.allclose(hi, mhi)


def test_render_views(default_result):
    mesh = build_mesh(default_result.bbmodel)
    for key, view in VIEWS.items():
        img = render(mesh, default_result.texture, view, size=160, background=None)
        assert img.shape == (160, 160, 4)
        assert (img[..., 3] > 0).mean() > 0.04, key
    a = render(mesh, default_result.texture, VIEWS["frente"], size=120)
    b = render(mesh, default_result.texture, VIEWS["frente"], size=120)
    assert np.array_equal(a, b)


def test_side_view_shows_eye_color(default_result):
    mesh = build_mesh(default_result.bbmodel)
    img = render(mesh, default_result.texture, VIEWS["lado_direito"], size=500, shading=False)
    from ninho_studio.palette import hex_to_rgb

    eye = np.array(hex_to_rgb(default_result.spec["colors"]["eyes"]))
    close = (np.abs(img[..., :3].astype(int) - eye).sum(axis=2) < 30) & (img[..., 3] > 0)
    assert close.sum() > 10


def test_sheets_and_viewer(default_result):
    mesh = build_mesh(default_result.bbmodel)
    assert contact_sheet(mesh, default_result.texture, cell=140).size[0] == 420
    w, h = atlas_debug(default_result.bbmodel, default_result.texture, zoom=2).size
    assert w == default_result.atlas.size * 2 and h > default_result.atlas.size * 2  # + legenda
    assert skeleton_sheet(mesh, default_result.texture, size=200).size[1] > 200
    page = viewer_html(mesh, default_result.png, title="<teste>")
    assert "&lt;teste&gt;" in page and "webgl" in page and "http" not in page.split("<script>")[1].split("</script>")[0]
