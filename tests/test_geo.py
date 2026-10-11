"""Exportação .geo.json para o GeckoLib (Minecraft Java)."""

import copy
import json
import os
import zipfile

import numpy as np
import pytest

from ninho_studio.geo import (
    GECKOLIB_PATHS,
    GEO_FORMAT_VERSION,
    OneLiner,
    bbmodel_to_geo,
    calculate_visible_box,
    compile_json,
    geo_dumps,
    validate_geo,
)
from ninho_studio.pipeline import generate
from ninho_studio.spec import BuildSettings, default_spec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# .geo.json exportados pelo próprio Blockbench 5.2.2 (Codecs.bedrock.compile) a partir dos .bbmodel de exemplo
BLOCKBENCH_EXPORTS = [
    ("examples/trex-verde/trex_verde.bbmodel", "examples/trex-verde/blockbench/trex_verde.geo.json"),
    ("examples/trex-branco-ia/tyranos_rex.bbmodel", "examples/trex-branco-ia/blockbench/tyranos_rex.geo.json"),
]


def _load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("bbmodel_path,blockbench_geo", BLOCKBENCH_EXPORTS)
def test_geo_is_byte_identical_to_blockbench_export(bbmodel_path, blockbench_geo):
    bb = json.loads(_load(bbmodel_path))
    assert geo_dumps(bbmodel_to_geo(bb)) == _load(blockbench_geo)


@pytest.mark.parametrize("bbmodel_path,_", BLOCKBENCH_EXPORTS)
def test_example_packages_carry_the_same_geo(bbmodel_path, _):
    folder, name = os.path.split(bbmodel_path)
    stem = name[: -len(".bbmodel")]
    geo_text = _load(os.path.join(folder, stem + ".geo.json"))
    assert geo_text == geo_dumps(bbmodel_to_geo(json.loads(_load(bbmodel_path))))
    with zipfile.ZipFile(os.path.join(ROOT, folder, stem + ".zip")) as zf:
        assert zf.read(stem + ".geo.json").decode("utf-8") == geo_text


def test_geo_structure_and_sign_conventions(default_result):
    bb, geo = default_result.bbmodel, default_result.geo
    assert geo["format_version"] == GEO_FORMAT_VERSION == "1.12.0"
    (entity,) = geo["minecraft:geometry"]
    desc = entity["description"]
    assert desc["identifier"] == "geometry." + bb["model_identifier"]
    assert (desc["texture_width"], desc["texture_height"]) == (bb["resolution"]["width"], bb["resolution"]["height"])
    assert [desc["visible_bounds_width"], desc["visible_bounds_height"], desc["visible_bounds_offset"][1]] == bb["visible_box"]

    bones = entity["bones"]
    groups = {g["name"]: g for g in bb["groups"]}
    elements = {e["uuid"]: e for e in bb["elements"]}
    assert len(bones) == len(groups)
    assert sum(len(b.get("cubes", [])) for b in bones) == len(elements)
    seen = set()
    for bone in bones:
        g = groups[bone["name"]]
        assert bone.get("parent") is None or bone["parent"] in seen  # pai sempre antes do filho
        seen.add(bone["name"])
        assert bone["pivot"] == [-g["origin"][0], g["origin"][1], g["origin"][2]]
        if any(g["rotation"]):
            assert bone["rotation"] == [-g["rotation"][0], -g["rotation"][1], g["rotation"][2]]
        else:
            assert "rotation" not in bone
    for bone in bones:
        for cube in bone.get("cubes", []):
            assert isinstance(cube, OneLiner)
            matches = [e for e in elements.values()
                       if [-(e["from"][0] + (e["to"][0] - e["from"][0])), e["from"][1], e["from"][2]] == cube["origin"]
                       and [e["to"][i] - e["from"][i] for i in range(3)] == cube["size"]
                       and e.get("uv_offset", [0, 0]) == cube["uv"]]
            assert matches, cube


def _parse_back(geo):
    """Inverso do codec (parseBone/parseCube do Blockbench): volta para from/to/origem/rotação."""
    bones = {}
    for b in geo["minecraft:geometry"][0]["bones"]:
        rot = b.get("rotation", [0, 0, 0])
        cubes = []
        for c in b.get("cubes", []):
            frm = list(c["origin"])
            frm[0] = -(frm[0] + c["size"][0])
            cubes.append({"from": frm, "to": [frm[i] + c["size"][i] for i in range(3)], "uv_offset": c["uv"]})
        bones[b["name"]] = {"origin": [-b["pivot"][0], b["pivot"][1], b["pivot"][2]],
                            "rotation": [-rot[0], -rot[1], rot[2]], "parent": b.get("parent"), "cubes": cubes}
    return bones


def test_geo_parses_back_to_the_same_project(default_result):
    bb = default_result.bbmodel
    back = _parse_back(default_result.geo)
    groups = {g["uuid"]: g for g in bb["groups"]}
    elements = {e["uuid"]: e for e in bb["elements"]}

    def walk(nodes, parent):
        for node in nodes:
            g = groups[node["uuid"]]
            got = back[g["name"]]
            assert got["parent"] == parent
            assert got["origin"] == g["origin"] and got["rotation"] == [float(v) for v in g["rotation"]]
            own = [elements[c] for c in node["children"] if isinstance(c, str)]
            assert [(c["from"], c["to"], c["uv_offset"]) for c in got["cubes"]] == \
                   [(e["from"], e["to"], e.get("uv_offset", [0, 0])) for e in own]
            walk([c for c in node["children"] if isinstance(c, dict)], g["name"])

    walk(bb["outliner"], None)


def test_visible_box_matches_project(default_result):
    assert calculate_visible_box(default_result.bbmodel) == default_result.bbmodel["visible_box"]


def test_rotated_mirrored_and_inflated_cubes():
    """Ramos do codec que o T-rex atual não usa (conferidos no Blockbench; ver tools/verify_geckolib.py)."""
    bb = generate(default_spec(), BuildSettings(seed=1), mode="procedural").bbmodel
    bb = copy.deepcopy(bb)
    el = bb["elements"][0]
    el.update(rotation=[10, -20, 30], origin=[1.5, 2, -3], mirror_uv=True, inflate=0.25)
    cube = next(c for b in bbmodel_to_geo(bb)["minecraft:geometry"][0]["bones"] for c in b.get("cubes", [])
                if c["uv"] == el.get("uv_offset", [0, 0]) and c["size"] == [el["to"][i] - el["from"][i] for i in range(3)])
    assert list(cube) == ["origin", "size", "inflate", "pivot", "rotation", "uv", "mirror"]
    assert cube["pivot"] == [-1.5, 2, -3] and cube["rotation"] == [-10, 20, 30]
    assert cube["inflate"] == 0.25 and cube["mirror"] is True


def test_compile_json_follows_blockbench_rules():
    assert compile_json({"a": 1.0, "b": -0.0, "c": 19.5, "d": 1 / 3, "e": 0.00001, "f": 2.5e-6}) == \
        '{\n\t"a": 1,\n\t"b": 0,\n\t"c": 19.5,\n\t"d": 0.33333,\n\t"e": 0.00001,\n\t"f": 0\n}'
    assert compile_json({"cubes": [OneLiner(origin=[1, 2, 3], uv=[0, 0])]}) == \
        '{\n\t"cubes": [\n\t\t{"origin": [1, 2, 3], "uv": [0, 0]}\n\t]\n}'
    assert compile_json({"t": 'a"b\\c\nd\te'}) == '{\n\t"t": "a\\"b\\\\c\\nd\\te"\n}'
    long = list(range(60))  # 60 números * 3 > 140 → uma linha por item
    assert compile_json(long).count("\n") == 61
    assert compile_json({"e": {}, "l": []}) == '{\n\t"e": {},\n\t"l": []\n}'


def test_validate_geo_catches_geckolib_problems(default_result):
    geo = copy.deepcopy(default_result.geo)
    assert validate_geo(geo, (default_result.atlas.size,) * 2) == []
    bones = geo["minecraft:geometry"][0]["bones"]
    bones[2]["name"] = bones[1]["name"]
    bones[3]["parent"] = "nao_existe"
    cube = next(b for b in bones if b.get("cubes"))["cubes"][0]
    cube["size"] = [1.5, 2, 2]
    cube["uv"] = [500, 0]
    geo["format_version"] = "1.21.0"
    problems = "\n".join(validate_geo(geo, (64, 64)))
    for expected in ("repetido", "nao_existe", "não inteiro", "sai da textura", "1.21.0", "difere do PNG"):
        assert expected in problems, expected

    cyc = copy.deepcopy(default_result.geo)
    b = cyc["minecraft:geometry"][0]["bones"]
    b[0]["parent"] = b[1]["name"]
    assert any("ciclo" in p for p in validate_geo(cyc))


@pytest.mark.parametrize("detail", ["low", "medium", "high"])
def test_every_detail_level_exports_valid_geo(detail):
    spec = default_spec()
    spec["detail_level"] = detail
    spec["features"].update(back_spikes=True, feather_crest=True, brow_horns=True)
    res = generate(spec, BuildSettings(seed=5), mode="procedural")
    assert validate_geo(res.geo, (res.atlas.size, res.atlas.size)) == []
    assert "geo.json do GeckoLib" in res.validation.checks and res.validation.ok


def test_saved_outputs_contain_geo(default_result, tmp_path):
    from ninho_studio.export import save_outputs

    paths = save_outputs(default_result, str(tmp_path), previews=False, viewer=False)
    name = default_result.base_name
    with open(paths["geo"], encoding="utf-8") as fh:
        text = fh.read()
    assert text == default_result.geo_text and json.loads(text) == json.loads(json.dumps(default_result.geo))
    with zipfile.ZipFile(paths["zip"]) as zf:
        assert f"{name}.geo.json" in zf.namelist()
        readme = zf.read("LEIA-ME.txt").decode("utf-8")
    assert "geckolib/models/entity" in readme and "geo/entity" in readme
    import hashlib

    assert default_result.config["files"]["sha256"][f"{name}.geo.json"] == hashlib.sha256(text.encode()).hexdigest()
    java = default_result.config["minecraft_java"]
    assert java["paths_in_mod"]["geckolib5"]["model"] == f"assets/<modid>/geckolib/models/entity/{name}.geo.json"
    assert set(GECKOLIB_PATHS) == {"geckolib4", "geckolib5"}


def test_geo_bounds_match_mesh(default_result):
    from ninho_studio.mesh import build_mesh

    from ninho_studio.geo import _exported_corners

    lo, hi = build_mesh(default_result.bbmodel).bounds
    pts = _exported_corners(default_result.bbmodel)
    assert np.allclose(pts.min(axis=0), lo) and np.allclose(pts.max(axis=0), hi)
