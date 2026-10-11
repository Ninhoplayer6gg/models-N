import copy

import pytest

from ninho_studio.validate import validate_bbmodel


def codes(report, level="erro"):
    return {i.code for i in report.issues if i.level == level}


def test_generated_model_is_clean(default_result):
    rep = validate_bbmodel(default_result.bbmodel, element_budget=64)
    assert rep.ok, rep.summary_pt()
    assert not rep.warnings, rep.summary_pt()
    assert rep.stats["faces_sem_pintura"] == 0


def mutate(bb, fn):
    bb = copy.deepcopy(bb)
    fn(bb)
    return validate_bbmodel(bb)


@pytest.mark.parametrize(
    "name, fn, code",
    [
        ("uuid duplicado", lambda bb: bb["elements"][1].__setitem__("uuid", bb["elements"][0]["uuid"]), "uuid"),
        ("uuid inválido", lambda bb: bb["groups"][0].__setitem__("uuid", "abc"), "uuid"),
        ("tamanho negativo", lambda bb: bb["elements"][0].__setitem__("to", [-100, 0, 0]), "dimensoes"),
        ("coordenada não finita", lambda bb: bb["elements"][0].__setitem__("from", [float("nan"), 0, 0]), "dimensoes"),
        ("UV fora", lambda bb: bb["elements"][0]["faces"]["north"].__setitem__("uv", [120, 120, 140, 140]), "uv"),
        ("textura inexistente", lambda bb: bb["elements"][0]["faces"]["up"].__setitem__("texture", 3), "referencias"),
        ("nome de osso duplicado", lambda bb: bb["groups"][2].__setitem__("name", bb["groups"][1]["name"]), "nomes"),
        ("cubo fora do outliner", lambda bb: bb["outliner"][0]["children"].clear(), "hierarquia"),
        ("referência inexistente", lambda bb: bb["outliner"].append("00000000-0000-4000-8000-000000000000"), "referencias"),
        ("grupo repetido", lambda bb: bb["outliner"].append(copy.deepcopy(bb["outliner"][0])), "hierarquia"),
        ("formato errado", lambda bb: bb["meta"].__setitem__("format_version", "4.0"), "formato"),
        ("orçamento", None, "orcamento"),
    ],
)
def test_injected_errors_are_detected(default_result, name, fn, code):
    if fn is None:
        rep = validate_bbmodel(default_result.bbmodel, element_budget=5)
    else:
        rep = mutate(default_result.bbmodel, fn)
    assert not rep.ok, name
    assert code in codes(rep), (name, rep.summary_pt())


def test_box_uv_inconsistency_and_unpainted_face(default_result):
    def shift_uv(bb):
        bb["elements"][0]["uv_offset"] = [1, 1]

    rep = mutate(default_result.bbmodel, shift_uv)
    assert "uv" in codes(rep)

    import numpy as np

    tex = default_result.texture.copy()
    el = default_result.bbmodel["elements"][0]
    u0, v0, u1, v1 = el["faces"]["north"]["uv"]
    tex[int(min(v0, v1)):int(max(v0, v1)), int(min(u0, u1)):int(max(u0, u1)), 3] = 0
    rep = validate_bbmodel(default_result.bbmodel, texture=tex)
    assert "pintura" in codes(rep)
    assert np.any(tex[..., 3] == 0)


def test_pivot_far_and_ground_warnings(default_result):
    def move_pivot(bb):
        for g in bb["groups"]:
            if g["name"] == "jaw":
                g["origin"] = [0, 200, 0]

    rep = mutate(default_result.bbmodel, move_pivot)
    assert "pivo" in codes(rep, "aviso")

    def sink(bb):
        for el in bb["elements"]:
            el["from"][1] -= 5
            el["to"][1] -= 5

    rep = mutate(default_result.bbmodel, sink)
    assert "chao" in codes(rep, "aviso")
