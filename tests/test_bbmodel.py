import json

import numpy as np

from ninho_studio.bbmodel import compute_visible_box, dumps, sanitize_identifier, texture_array
from ninho_studio.model import Model

# Chaves gravadas pelo Blockbench 5.2.2 num projeto Bedrock de referência
# (sem os campos de estado de seleção da interface).
TOP_KEYS = ["meta", "name", "model_identifier", "visible_box", "variable_placeholders", "multi_file_ruleset",
            "variable_placeholder_buttons", "bedrock_animation_mode", "timeline_setups", "unhandled_root_fields",
            "resolution", "elements", "groups", "outliner", "textures"]
ELEMENT_KEYS = {"name", "box_uv", "render_order", "locked", "export", "scope", "allow_mirror_modeling", "from", "to",
                "autouv", "color", "origin", "faces", "type", "uuid"}
ELEMENT_OPTIONAL = {"uv_offset", "rotation", "mirror_uv", "inflate"}
GROUP_KEYS = {"name", "uuid", "export", "locked", "scope", "visibility", "origin", "rotation", "bedrock_binding", "color",
              "children", "reset", "shade", "mirror_uv", "autouv", "isOpen"}
TEXTURE_KEYS = {"name", "path", "folder", "namespace", "id", "group", "scope", "width", "height", "uv_width",
                "uv_height", "particle", "use_as_default", "layers_enabled", "sync_to_project", "file_format",
                "render_mode", "render_sides", "wrap_mode", "pbr_channel", "fps", "force_translucent", "frame_time",
                "frame_order_type", "frame_order", "frame_interpolate", "visible", "internal", "saved", "uuid", "source"}


def test_structure_matches_blockbench_reference(default_result):
    bb = default_result.bbmodel
    assert list(bb.keys()) == TOP_KEYS
    assert bb["meta"] == {"format_version": "5.0", "model_format": "bedrock", "box_uv": True}
    for el in bb["elements"]:
        keys = set(el)
        assert ELEMENT_KEYS <= keys and keys <= ELEMENT_KEYS | ELEMENT_OPTIONAL, keys ^ ELEMENT_KEYS
        assert list(el["faces"]) == ["north", "east", "south", "west", "up", "down"]
        assert all(set(f) == {"uv", "texture"} and f["texture"] == 0 for f in el["faces"].values())
    for g in bb["groups"]:
        assert set(g) == GROUP_KEYS
        assert g["children"] == []
    assert set(bb["textures"][0]) == TEXTURE_KEYS


def test_outliner_references_everything_once(default_result):
    bb = default_result.bbmodel
    seen_el, seen_g = [], []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, str):
                seen_el.append(n)
            else:
                assert set(n) == {"uuid", "isOpen", "children"}
                seen_g.append(n["uuid"])
                walk(n["children"])

    walk(bb["outliner"])
    assert sorted(seen_el) == sorted(e["uuid"] for e in bb["elements"])
    assert sorted(seen_g) == sorted(g["uuid"] for g in bb["groups"])


def test_texture_embedded_equals_png(default_result):
    bb = default_result.bbmodel
    arr = texture_array(bb)
    assert np.array_equal(arr, default_result.texture)
    tex = bb["textures"][0]
    assert (tex["width"], tex["height"]) == (default_result.atlas.size, default_result.atlas.size)
    assert bb["resolution"] == {"width": tex["uv_width"], "height": tex["uv_height"]}


def test_json_roundtrip_is_stable(default_result):
    text = dumps(default_result.bbmodel)
    assert json.loads(text) == default_result.bbmodel


def test_visible_box_matches_blockbench_reference():
    # Mesmo projeto de referência montado no Blockbench 5.2.2, cujo calculateVisibleBox() deu [2, 2.5, 0.75]
    m = Model("ref", 64)
    m.add_bone("body", (0, 12, 0), (10, 0, 0))
    m.add_bone("head", (0, 16, -6), parent="body")
    m.add_cube("body", "torso", (-4, 8, -6), (8, 8, 12), "torso", origin=(0, 12, 0))
    m.add_cube("head", "skull", (-3, 14, -12), (6, 6, 6), "skull", origin=(0, 16, -6))
    assert compute_visible_box(m) == [2, 2.5, 0.75]


def test_identifier_sanitized():
    assert sanitize_identifier("T-rex Verde Ação!") == "t_rex_verde_acao"
    assert sanitize_identifier("***") == "ninho_model"
