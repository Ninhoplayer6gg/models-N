"""Gera o exemplo do T-rex verde e a galeria de variações (modo procedural).

Uso:  python tools/make_example.py

O exemplo é gerado no modo PROCEDURAL, com parâmetros escritos à mão que
correspondem à descrição. (Neste ambiente de desenvolvimento não foi possível
baixar os pesos do Qwen; ver docs/RELATORIO-DE-TESTES.md.)
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw  # noqa: E402

from ninho_studio.export import save_outputs  # noqa: E402
from ninho_studio.mesh import build_mesh  # noqa: E402
from ninho_studio.pipeline import generate  # noqa: E402
from ninho_studio.render import View, _font, render  # noqa: E402
from ninho_studio.spec import BuildSettings, apply_adjustments, default_spec  # noqa: E402

DESCRIPTION = "Um T-rex verde, com listras escuras nas costas, barriga creme, olhos amarelos e boca entreaberta."


def example() -> None:
    spec = default_spec()
    spec["name"] = "T-rex verde"
    result = generate(spec, BuildSettings(seed=42, texture_size=128, element_budget=64), mode="procedural",
                      description=DESCRIPTION, base_name="trex_verde")
    out = os.path.join(ROOT, "examples", "trex-verde")
    paths = save_outputs(result, out)
    print(result.validation.summary_pt())
    for key, path in paths.items():
        print(f"{key:10s} {os.path.relpath(path, ROOT)}")


VARIANTS = [
    ("Padrão (verde, listras)", {}),
    ("Filhote marrom com manchas", {"scale": 0.75, "proportions": {"head_size": 1.25, "tail_length": 0.8},
                                    "colors": {"primary": "#8a6a44", "secondary": "#a8875d", "pattern": "#3e2a1c",
                                               "belly": "#efe2c4"},
                                    "pattern_type": "spots", "detail_level": "low", "jaw_open": 0.0}),
    ("Cinza blindado com espinhos", {"proportions": {"body_bulk": 1.25, "leg_thickness": 1.2},
                                     "colors": {"primary": "#5d6166", "secondary": "#7d8086", "pattern": "#2b2d31",
                                                "belly": "#c9c4b6", "eyes": "#e0402a"},
                                     "pattern_type": "bands", "skin": "rough", "detail_level": "high",
                                     "features": {"back_spikes": True, "brow_horns": True, "scars": True},
                                     "jaw_open": 1.0}),
    ("Emplumado azul com crista", {"proportions": {"neck_length": 1.3, "arm_length": 1.6, "tail_length": 1.3},
                                   "colors": {"primary": "#2e5c8a", "secondary": "#4f86b8", "pattern": "#f0a030",
                                              "belly": "#e6eef2"},
                                   "pattern_type": "mottled", "skin": "feathered", "detail_level": "high",
                                   "features": {"feather_crest": True}}),
]


def gallery() -> None:
    tiles = []
    for label, adj in VARIANTS:
        spec, _notes = apply_adjustments(default_spec(), adj)
        res = generate(spec, BuildSettings(seed=7, element_budget=64), mode="procedural")
        assert res.validation.ok, res.validation.summary_pt()
        mesh = build_mesh(res.bbmodel)
        img = Image.fromarray(render(mesh, res.texture, View("p", (0.85, 0.4, -0.85), ortho=False, fov=26), size=420))
        d = ImageDraw.Draw(img)
        d.text((12, 10), f"{label}\n{res.model.cube_count} cubos · textura {res.atlas.size}", fill=(30, 30, 30, 255),
               font=_font(17))
        tiles.append(img)
    sheet = Image.new("RGB", (420 * 2, 420 * 2), "white")
    for k, tile in enumerate(tiles):
        sheet.paste(tile.convert("RGB"), ((k % 2) * 420, (k // 2) * 420))
    path = os.path.join(ROOT, "docs", "img", "variacoes.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    print("galeria:", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    example()
    gallery()
