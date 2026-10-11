import copy

import pytest

from ninho_studio.spec import (
    PROPORTIONS,
    BuildSettings,
    SpecValidationError,
    apply_adjustments,
    default_spec,
    json_schema,
    normalize_hex,
    normalize_spec,
    validate_spec,
)


def test_default_spec_is_valid():
    assert validate_spec(default_spec()) == []


def test_partial_spec_is_completed_with_defaults():
    spec, provided = normalize_spec({"species": "t_rex", "colors": {"primary": "#AABBCC"}})
    assert spec["colors"]["primary"] == "#aabbcc"
    assert spec["proportions"]["head_size"] == 1.0
    assert provided == ["colors.primary", "species"]


@pytest.mark.parametrize(
    "patch, path_fragment",
    [
        ({"proportions": {"head_size": 2.5}}, "proportions.head_size"),
        ({"proportions": {"head_size": "grande"}}, "proportions.head_size"),
        ({"proportions": {"head_size": True}}, "proportions.head_size"),
        ({"colors": {"primary": "verde"}}, "colors.primary"),
        ({"colors": {"primary": "#12345"}}, "colors.primary"),
        ({"pattern": {"type": "zebra"}}, "pattern.type"),
        ({"skin": "metal"}, "skin"),
        ({"detail_level": "ultra"}, "detail_level"),
        ({"features": {"back_spikes": "sim"}}, "features.back_spikes"),
        ({"proportions": {"cabeca": 1.2}}, "proportions.cabeca"),
        ({"wings": True}, "wings"),
        ({"species": "dragon"}, "species"),
        ({"scale": 3}, "scale"),
        ({"name": ""}, "name"),
        ({"name": "x" * 41}, "name"),
        ({"pattern": {"intensity": -0.1}}, "pattern.intensity"),
    ],
)
def test_invalid_values_are_rejected_with_path(patch, path_fragment):
    obj = {"species": "t_rex"}
    for key, value in patch.items():
        obj[key] = value
    errors = validate_spec(obj)
    assert errors, patch
    assert any(e.path == path_fragment for e in errors), [str(e) for e in errors]


def test_missing_species_and_non_object():
    assert any(e.path == "species" for e in validate_spec({}))
    assert validate_spec([1, 2])
    with pytest.raises(SpecValidationError):
        normalize_spec({"species": "t_rex", "scale": 99})


def test_matches_official_jsonschema_library():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(json_schema())
    good = default_spec()
    cases = [good, {"species": "t_rex"}, {"species": "t_rex", "scale": 0.6}, {"species": "t_rex", "scale": 1.6}]
    bad_patches = [
        ("scale", 0.59), ("scale", "1"), ("skin", "lisa"), ("extra", 1), ("species", "raptor"),
        ("pattern", {"type": "stripes", "intensity": 2}), ("colors", {"eyes": "#zzzzzz"}),
        ("features", {"scars": 1}), ("proportions", {"tail_length": None}),
    ]
    for key, value in bad_patches:
        obj = copy.deepcopy(good)
        obj[key] = value
        cases.append(obj)
    for obj in cases:
        official_ok = validator.is_valid(obj)
        ours_ok = not validate_spec(obj)
        assert official_ok == ours_ok, obj


def test_apply_adjustments_multiplies_and_clamps():
    spec = default_spec()
    out, notes = apply_adjustments(spec, {"proportions": {"head_size": 1.2, "tail_length": 5.0}, "scale": 1.0})
    assert out["proportions"]["head_size"] == pytest.approx(1.2)
    lo, hi, _d, _desc = PROPORTIONS["tail_length"]
    assert out["proportions"]["tail_length"] == hi
    assert any("tail_length" in n for n in notes)
    assert spec["proportions"]["head_size"] == 1.0  # não altera a original


def test_apply_adjustments_overrides():
    out, _ = apply_adjustments(default_spec(), {
        "colors": {"primary": "c33"}, "pattern_type": "spots", "skin": "rough", "detail_level": "high",
        "features": {"back_spikes": True, "scars": None}, "jaw_open": 1.0, "name": "Rex",
    })
    assert out["colors"]["primary"] == "#cc3333"
    assert out["pattern"]["type"] == "spots"
    assert out["skin"] == "rough"
    assert out["detail_level"] == "high"
    assert out["features"]["back_spikes"] is True
    assert out["features"]["scars"] is False
    assert out["proportions"]["jaw_open"] == 1.0
    assert out["name"] == "Rex"
    with pytest.raises(ValueError):
        apply_adjustments(default_spec(), {"colors": {"primary": "verde"}})


def test_normalize_hex():
    assert normalize_hex("#ABC") == "#aabbcc"
    assert normalize_hex("4f7a35") == "#4f7a35"
    with pytest.raises(ValueError):
        normalize_hex("#12")


def test_build_settings_validation():
    assert BuildSettings().validate() == []
    assert BuildSettings(texture_size=64).validate()
    assert BuildSettings(element_budget=4).validate()
