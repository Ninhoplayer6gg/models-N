import json
import os
import zipfile

import pytest

from ninho_studio.export import save_outputs
from ninho_studio.pipeline import generate, regenerate_from_config
from ninho_studio.spec import BuildSettings, default_spec


def test_config_contents(default_result):
    cfg = default_result.config
    for key in ("version", "spec_version", "mode", "description", "seed", "parameters", "settings", "validation",
                "files", "blockbench"):
        assert key in cfg
    assert cfg["mode"] == "procedural" and cfg["ai"] is None
    assert cfg["description"] == "teste"
    assert cfg["blockbench"]["format_version"] == "5.0"
    assert cfg["validation"]["ok"] is True
    json.dumps(cfg)  # serializável


def test_reproducible_from_config(default_result):
    again = regenerate_from_config(json.loads(json.dumps(default_result.config)))
    assert again.png == default_result.png
    assert again.config["files"]["sha256"] == default_result.config["files"]["sha256"]


def test_mode_rules():
    with pytest.raises(ValueError):
        generate(default_spec(), BuildSettings(), mode="magia")
    with pytest.raises(ValueError):
        generate(default_spec(), BuildSettings(), mode="ia")  # IA exige informações da execução
    res = generate(default_spec(), BuildSettings(), mode="ia", ai_info={"model": {"model_id": "x"}})
    assert res.config["mode"] == "ia" and res.config["ai"]["model"]["model_id"] == "x"


def test_texture_upgrade_and_forced_256():
    spec = default_spec()
    spec["scale"] = 1.6
    spec["detail_level"] = "high"
    res = generate(spec, BuildSettings(texture_size=128, element_budget=96), mode="procedural")
    assert res.atlas.size == 256 and res.atlas.upgraded
    assert any("256" in n for n in res.notes)
    assert res.validation.ok
    res2 = generate(default_spec(), BuildSettings(texture_size=256), mode="procedural")
    assert res2.atlas.size == 256 and not res2.atlas.upgraded
    assert res2.texture.shape == (256, 256, 4)


def test_save_outputs(tmp_path, default_result):
    paths = save_outputs(default_result, str(tmp_path))
    for key in ("bbmodel", "png", "json", "vistas", "atlas", "esqueleto", "html", "zip"):
        assert os.path.exists(paths[key]), key
    with zipfile.ZipFile(paths["zip"]) as zf:
        names = set(zf.namelist())
    name = default_result.base_name
    assert {f"{name}.bbmodel", f"{name}.png", f"{name}.json"} <= names
    with open(paths["bbmodel"], encoding="utf-8") as fh:
        assert json.load(fh) == default_result.bbmodel


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_many_seeds_validate(seed):
    for detail in ("low", "medium", "high"):
        spec = default_spec()
        spec["detail_level"] = detail
        res = generate(spec, BuildSettings(seed=seed), mode="procedural")
        assert res.validation.ok, res.validation.summary_pt()
        assert not res.validation.warnings, res.validation.summary_pt()


def test_extreme_proportions_validate():
    for value in ("min", "max"):
        spec = default_spec()
        from ninho_studio.spec import PROPORTIONS

        for key, (lo, hi, _d, _desc) in PROPORTIONS.items():
            spec["proportions"][key] = lo if value == "min" else hi
        spec["scale"] = 0.6 if value == "min" else 1.6
        res = generate(spec, BuildSettings(element_budget=96), mode="procedural")
        assert res.validation.ok, (value, res.validation.summary_pt())
        if value == "max":  # não cabe em 256 na escala 1.6: reduz a escala e avisa
            assert res.spec["scale"] < 1.6 and res.atlas.size == 256
            assert any("escala reduzida" in n for n in res.notes)
            assert res.config["parameters"]["scale"] == res.spec["scale"]


def test_color_notes_for_low_contrast_belly():
    from ninho_studio.pipeline import color_notes

    spec = default_spec()
    assert color_notes(spec) == []
    spec["colors"].update(primary="#ffffff", belly="#fffbe8")
    notes = color_notes(spec)
    assert notes and "cor_barriga" in notes[0]
