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


def side_by_side(bbmodel_path: str, shots_dir: str, out_path: str) -> None:
    """Imagem com a prévia do Ninho (esquerda) e a captura do Blockbench (direita) para cada vista."""
    from PIL import ImageDraw

    from ninho_studio.render import _font

    bb = json.load(open(bbmodel_path, encoding="utf-8"))
    mesh = build_mesh(bb)
    tex = texture_array(bb)
    rows = []
    for key, label in (("perspectiva", "Perspectiva"), ("lado_direito", "Lado direito"), ("frente", "Frente")):
        ours = Image.fromarray(render(mesh, tex, VIEWS[key], size=400, background=(255, 255, 255, 255))).convert("RGB")
        shot = Image.open(os.path.join(shots_dir, f"bb_{key}.png")).convert("RGBA")
        shot = Image.alpha_composite(Image.new("RGBA", shot.size, (255, 255, 255, 255)), shot).convert("RGB")
        arr = np.array(shot)
        ys, xs = np.nonzero((arr < 250).any(axis=2))
        pad = 30
        crop = shot.crop((max(xs.min() - pad, 0), max(ys.min() - pad, 0), min(xs.max() + pad, shot.width),
                          min(ys.max() + pad, shot.height)))
        k = 400 / max(crop.size)
        crop = crop.resize((int(crop.width * k), int(crop.height * k)))
        tile = Image.new("RGB", (400, 400), "white")
        tile.paste(crop, ((400 - crop.width) // 2, (400 - crop.height) // 2))
        row = Image.new("RGB", (800, 430), "white")
        d = ImageDraw.Draw(row)
        font = _font(17)
        d.text((10, 6), f"{label}: prévia do Ninho", fill=(20, 20, 20), font=font)
        d.text((410, 6), f"{label}: Blockbench 5.2.2", fill=(20, 20, 20), font=font)
        row.paste(ours, (0, 30))
        row.paste(tile, (400, 30))
        rows.append(row)
    sheet = Image.new("RGB", (800, 430 * len(rows)), "white")
    for i, r in enumerate(rows):
        sheet.paste(r, (0, i * 430))
    sheet.save(out_path)


if __name__ == "__main__":
    result = compare(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
    if len(sys.argv) > 3:
        side_by_side(sys.argv[1], sys.argv[2], sys.argv[3])
