"""Gera várias variantes e verifica cada uma no Blockbench (build web local).

Uso (com a build web do Blockbench servida em 127.0.0.1:8765; ver tools/README.md):

    python tools/verify_variants.py [--playwright /caminho/playwright/index.mjs]

Resultado: docs/verificacao-blockbench-variantes.json
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from compare_renders import compare  # noqa: E402
from make_example import VARIANTS  # noqa: E402

from ninho_studio import __version__  # noqa: E402
from ninho_studio.bbmodel import dumps  # noqa: E402
from ninho_studio.pipeline import generate  # noqa: E402
from ninho_studio.spec import BuildSettings, apply_adjustments, default_spec  # noqa: E402


def cases():
    for i, (label, adj) in enumerate(VARIANTS):
        spec, _ = apply_adjustments(default_spec(), adj)
        yield f"galeria_{i}", label, spec, BuildSettings(seed=7)
    for detail in ("low", "medium", "high"):
        spec = default_spec()
        spec["detail_level"] = detail
        yield f"detalhe_{detail}", f"detalhe {detail}", spec, BuildSettings(seed=11)
    spec = default_spec()
    spec["scale"] = 1.4
    yield "textura_256", "escala 1.4, textura 256", spec, BuildSettings(seed=3, texture_size=256)
    spec = default_spec()
    spec["proportions"]["head_size"] = 1.4
    spec["colors"].update(primary="#ffffff", secondary="#f2f2f2", belly="#fffbe8", pattern="#333333", eyes="#ff6347")
    yield "branco_cabeca_grande", "branco, cabeça 1.4 (caso do teste real)", spec, BuildSettings(seed=42)


def main() -> None:
    extra = sys.argv[1:]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for key, label, spec, settings in cases():
            res = generate(spec, settings, mode="procedural", base_name=key)
            path = os.path.join(tmp, key + ".bbmodel")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(dumps(res.bbmodel))
            out = os.path.join(tmp, "check_" + key)
            subprocess.run(["node", os.path.join(ROOT, "tools", "blockbench_check.mjs"), "--model", path, "--out", out,
                            *extra], check=True, capture_output=True, timeout=600)
            with open(os.path.join(out, "blockbench_report.json"), encoding="utf-8") as fh:
                r = json.load(fh)
            rows.append({
                "variante": label, "cubos": r["cubes"], "grupos": r["groups"], "formato": r["format"],
                "textura": [r["texture"]["width"], r["texture"]["height"]], "textura_carregada": r["texture"]["loaded"],
                "estrategia_atlas": res.atlas.strategy,
                "avisos_validador_blockbench": r["validator_warnings"], "erros_validador_blockbench": r["validator_errors"],
                "mensagens_de_erro": r["message_boxes"], "erros_console": r["console_errors_after_load"],
                "diferencas_ida_e_volta": r["roundtrip_differences"], "exportacao_bedrock": r["bedrock_export"],
                "visible_box_igual": r["visible_box_file"] == r["visible_box_blockbench"],
                "iou_silhuetas": compare(path, out),
            })
            print(key, rows[-1]["textura"], len(r["validator_warnings"]), len(r["validator_errors"]),
                  rows[-1]["iou_silhuetas"])
    doc = {
        "blockbench": "5.2.2 (build web oficial compilada do código-fonte, commit 7c92e27, aberta em Chromium sem tela)",
        "ninho_model_studio": __version__,
        "data": dt.date.today().isoformat(),
        "variantes": rows,
    }
    with open(os.path.join(ROOT, "docs", "verificacao-blockbench-variantes.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
