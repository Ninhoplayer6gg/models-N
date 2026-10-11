"""Confere o .geo.json (GeckoLib / Minecraft Java) no Blockbench para muitos modelos.

Para cada caso (os 2 exemplos, as 9 variantes de verify_variants.py e um caso sintético com
cubo girado, cubo espelhado, cubo inflado e osso espelhado — recursos que o T-rex atual não usa;
12 casos ao todo):
  * o Blockbench exporta o .bbmodel e o texto precisa ser IDÊNTICO ao nosso .geo.json;
  * o .geo.json é aberto sozinho (importação Bedrock) com o .png e comparado com o projeto
    (ossos, pivôs, rotações, cubos, UV das faces, caixa do modelo) e por capturas de tela.

Uso (com a build web do Blockbench servida em 127.0.0.1:8765; ver tools/README.md):

    python tools/verify_geckolib.py [--playwright /caminho/playwright/index.mjs]

Resultado: docs/verificacao-geckolib.json
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from verify_variants import cases as variant_cases  # noqa: E402

from ninho_studio import __version__  # noqa: E402
from ninho_studio.bbmodel import dumps  # noqa: E402
from ninho_studio.geo import bbmodel_to_geo, geo_dumps  # noqa: E402
from ninho_studio.pipeline import generate  # noqa: E402
from ninho_studio.spec import BuildSettings, default_spec  # noqa: E402
from ninho_studio.uv import FACES, box_uv_face_rects  # noqa: E402

EXAMPLES = [
    ("exemplo_trex_verde", "exemplo T-rex verde", "examples/trex-verde/trex_verde"),
    ("exemplo_trex_branco", "exemplo T-rex branco (IA no Colab)", "examples/trex-branco-ia/tyranos_rex"),
]


def _read(path: str, mode: str = "r"):
    with open(os.path.join(ROOT, path), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as fh:
        return fh.read()


def synthetic_case():
    """T-rex padrão com recursos extras do codec: rotação de cubo, espelho (cubo e osso) e inflate."""
    res = generate(default_spec(), BuildSettings(seed=21), mode="procedural", base_name="sintetico")
    bb = copy.deepcopy(res.bbmodel)
    els = {e["name"]: e for e in bb["elements"]}
    rotated = els["snout"] if "snout" in els else bb["elements"][1]
    rotated["rotation"] = [10, -20, 30]
    rotated["origin"] = [1.5, 30, -30]
    mirrored = bb["elements"][2]
    mirrored["mirror_uv"] = True
    mirrored["faces"] = {f: {"uv": r, "texture": 0} for f, r in
                         box_uv_face_rects(mirrored["from"], mirrored["to"], mirrored.get("uv_offset", [0, 0]), True).items()}
    bb["elements"][3]["inflate"] = 0.25
    group = next(g for g in bb["groups"] if g["name"] == "arm_left")
    group["mirror_uv"] = True
    assert set(mirrored["faces"]) == set(FACES)
    return bb, geo_dumps(bbmodel_to_geo(bb)), res.png


def all_cases():
    for key, label, stem in EXAMPLES:
        yield key, label, json.loads(_read(stem + ".bbmodel")), _read(stem + ".geo.json"), _read(stem + ".png", "rb")
    for key, label, spec, settings in variant_cases():
        res = generate(spec, settings, mode="procedural", base_name=key)
        yield key, label, res.bbmodel, res.geo_text, res.png
    bb, geo_text, png = synthetic_case()
    yield "sintetico", "sintético: cubo girado, cubo e osso espelhados, cubo inflado", bb, geo_text, png


def pixel_stats(report: dict) -> dict:
    out = {}
    for view, a_path in report["screenshots"]["projeto"].items():
        a = np.asarray(Image.open(a_path).convert("RGB")).astype(int)
        b = np.asarray(Image.open(report["screenshots"]["geo"][view]).convert("RGB")).astype(int)
        diff = np.abs(a - b).sum(axis=2) > 0
        out[view] = {"pixels_diferentes": int(diff.sum()), "fracao": round(float(diff.mean()), 6)}
    return out


def main() -> None:
    extra = sys.argv[1:]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for key, label, bb, geo_text, png in all_cases():
            paths = {ext: os.path.join(tmp, f"{key}{ext}") for ext in (".bbmodel", ".geo.json", ".png")}
            with open(paths[".bbmodel"], "w", encoding="utf-8") as fh:
                fh.write(dumps(bb))
            with open(paths[".geo.json"], "w", encoding="utf-8") as fh:
                fh.write(geo_text)
            with open(paths[".png"], "wb") as fh:
                fh.write(png)
            out = os.path.join(tmp, "check_" + key)
            subprocess.run(["node", os.path.join(ROOT, "tools", "geo_check.mjs"), "--bbmodel", paths[".bbmodel"],
                            "--geo", paths[".geo.json"], "--png", paths[".png"], "--out", out, *extra],
                           check=True, capture_output=True, timeout=600)
            with open(os.path.join(out, "geo_report.json"), encoding="utf-8") as fh:
                r = json.load(fh)
            rows.append({
                "caso": label,
                "cubos": r["project"]["cubes"],
                "ossos": r["project"]["groups"],
                "exportacao_do_blockbench_identica": r["export_identical_to_ours"],
                "reexportacao_apos_importar_identica": r["reexport_identical_to_ours"],
                "importacao_geo": {k: r["geo_import"][k] for k in ("format", "cubes", "groups", "texture_size", "texture")},
                "diferencas_projeto_x_geo": r["differences"],
                "erros_validador_blockbench": r["geo_import"]["validator_errors"],
                "avisos_validador_blockbench": r["geo_import"]["validator_warnings"],
                "erros_console": r["console_errors"],
                "capturas_projeto_x_geo": pixel_stats(r),
            })
            worst = max(v["fracao"] for v in rows[-1]["capturas_projeto_x_geo"].values())
            print(key, rows[-1]["exportacao_do_blockbench_identica"], rows[-1]["reexportacao_apos_importar_identica"],
                  len(r["differences"]), len(r["geo_import"]["validator_errors"]), f"pixels {worst:.5f}")
    doc = {
        "blockbench": "5.2.2 (build web oficial compilada do código-fonte, commit 7c92e27, aberta em Chromium sem tela)",
        "ninho_model_studio": __version__,
        "data": dt.date.today().isoformat(),
        "o_que_foi_conferido": [
            "o texto exportado pelo Blockbench (Codecs.bedrock.compile, o mesmo usado pelo plugin do GeckoLib) "
            "é idêntico ao .geo.json do Ninho",
            "o .geo.json aberto sozinho (importação Bedrock) com o .png reproduz ossos, pivôs, rotações, cubos, "
            "UV das faces e caixa do modelo do projeto original",
            "reexportar depois de importar dá o mesmo texto",
            "capturas do projeto e do .geo.json com a mesma câmera (fração de pixels diferentes)",
        ],
        "casos": rows,
    }
    with open(os.path.join(ROOT, "docs", "verificacao-geckolib.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
