"""Faces coincidentes (z-fighting): detecção, correção no construtor e aviso no validador."""

import copy
import uuid

import numpy as np
import pytest

from ninho_studio.builders import build_model
from ninho_studio.coplanar import bbmodel_overlaps, find_overlaps, model_boxes, overlap_area
from ninho_studio.pipeline import generate
from ninho_studio.spec import BuildSettings, apply_adjustments, default_spec
from ninho_studio.validate import validate_bbmodel


def test_overlap_area_of_squares():
    n = np.array([0.0, 0.0, 1.0])
    a = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], dtype=float)
    b = a + [1, 1, 0]
    assert overlap_area(n, a, b) == pytest.approx(1.0)
    assert overlap_area(n, a, a + [3, 0, 0]) == pytest.approx(0.0)


def test_find_overlaps_only_same_facing_coplanar():
    eye = np.eye(4)
    # dois cubos lado a lado com a face de cima no mesmo plano e sobrepostas em x
    same = [("a", eye, (0, 0, 0), (4, 2, 4)), ("b", eye, (2, 0, 0), (6, 2, 4))]
    pairs = {(f1, f2) for _a, f1, _b, f2, _area in find_overlaps(same)}
    assert ("up", "up") in pairs and ("down", "down") in pairs
    # encostados costas com costas (face de cima de um = face de baixo do outro): não pisca
    stacked = [("a", eye, (0, 0, 0), (4, 2, 4)), ("b", eye, (0, 2, 0), (4, 4, 4))]
    assert not find_overlaps(stacked)
    # planos paralelos, mas separados por 0,05 px (o que o inflate faz): não pisca
    lifted = [("a", eye, (0, 0, 0), (4, 2, 4)), ("b", eye, (2, 0.05, 0), (6, 2.05, 4))]
    assert not [p for p in find_overlaps(lifted) if p[1] in ("up", "down")]


CASES = [
    ("medium", {}),
    ("low", {"jaw_open": 0.0}),
    ("high", {"features": {"back_spikes": True, "feather_crest": True, "brow_horns": True}}),
    ("high", {"proportions": {"head_size": 1.5, "leg_thickness": 0.7, "tail_thickness": 1.4}, "scale": 1.4}),
    ("medium", {"proportions": {"snout_length": 0.6, "neck_length": 0.6, "body_bulk": 0.7}, "scale": 0.6}),
]


@pytest.mark.parametrize("detail,adj", CASES)
def test_builder_leaves_no_coincident_faces(detail, adj):
    spec, _ = apply_adjustments(default_spec(), adj)
    spec["detail_level"] = detail
    model, _ = build_model(spec, BuildSettings(seed=3, element_budget=128))
    assert find_overlaps(model_boxes(model)) == []
    assert all(0 <= c.inflate <= 0.3 for c in model.iter_cubes())


def test_validator_warns_about_coincident_faces(default_result):
    bb = copy.deepcopy(default_result.bbmodel)
    assert bbmodel_overlaps(bb) == []
    # duplica um cubo deslocado 1 px para o lado: as faces de cima e de baixo coincidem
    original = next(e for e in bb["elements"] if e["name"] == "torso")
    el = copy.deepcopy(original)
    el["uuid"] = str(uuid.uuid4())
    el["name"] = "torso_copia"
    el["from"][0] += 1
    el["to"][0] += 1
    bb["elements"].append(el)

    def add_next_to(nodes):  # coloca a cópia no mesmo osso do original
        for node in nodes:
            if isinstance(node, dict):
                if original["uuid"] in node["children"]:
                    node["children"].append(el["uuid"])
                    return True
                if add_next_to(node["children"]):
                    return True
        return False

    assert add_next_to(bb["outliner"])
    rep = validate_bbmodel(bb, texture=default_result.texture)
    assert any(i.code == "coplanar" and "torso_copia" in i.message for i in rep.warnings)


def test_generated_models_validate_without_coplanar_warnings():
    for detail in ("low", "medium", "high"):
        spec = default_spec()
        spec["detail_level"] = detail
        res = generate(spec, BuildSettings(seed=8), mode="procedural")
        assert res.validation.stats["faces_coincidentes"] == 0
        assert not [w for w in res.validation.warnings if w.code == "coplanar"]
