"""Compara as silhuetas das capturas do Blockbench com o renderizador do Ninho.

Uso:  python tools/compare_renders.py modelo.bbmodel pasta_do_blockbench_check

Para cada vista ortográfica (lado direito, frente, topo) recorta a silhueta
(pixels não transparentes) das duas imagens, normaliza o tamanho e calcula o
IoU (interseção / união). Valores próximos de 1 indicam a mesma geometria,
pivôs e rotações.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ninho_studio.bbmodel import texture_array  # noqa: E402
from ninho_studio.mesh import build_mesh  # noqa: E402
from ninho_studio.render import VIEWS, render  # noqa: E402

SIZE = 256


def _mask(img: np.ndarray) -> np.ndarray:
    alpha = img[..., 3] > 127
    ys, xs = np.nonzero(alpha)
    crop = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    s = SIZE / max(h, w)
    im = Image.fromarray((crop * 255).astype(np.uint8)).resize((max(1, round(w * s)), max(1, round(h * s))), Image.NEAREST)
    out = np.zeros((SIZE, SIZE), dtype=bool)
    arr = np.array(im) > 127
    out[: arr.shape[0], : arr.shape[1]] = arr
    return out


def compare(bbmodel_path: str, shots_dir: str) -> dict:
    bb = json.load(open(bbmodel_path, encoding="utf-8"))
    mesh = build_mesh(bb)
    tex = texture_array(bb)
    result = {}
    for key in ("lado_direito", "frente", "topo"):
        shot = os.path.join(shots_dir, f"bb_{key}.png")
        if not os.path.exists(shot):
            continue
        bbimg = np.array(Image.open(shot).convert("RGBA"))
        ours = render(mesh, tex, VIEWS[key], size=600, background=None)
        a, b = _mask(bbimg), _mask(ours)
        iou = float((a & b).sum() / max(1, (a | b).sum()))
        result[key] = round(iou, 4)
    return result


if __name__ == "__main__":
    print(json.dumps(compare(sys.argv[1], sys.argv[2]), indent=2))
