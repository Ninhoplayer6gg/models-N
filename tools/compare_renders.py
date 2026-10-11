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


def pose_compare(bbmodel_path: str, shots_dir: str, pose_path: str, out_png: str) -> dict:
    """Aplica a mesma pose de teste do Blockbench na prévia do Ninho e compara a vista lateral."""
    import copy

    from PIL import ImageDraw

    from ninho_studio.render import _font

    bb = json.load(open(bbmodel_path, encoding="utf-8"))
    pose = json.load(open(pose_path, encoding="utf-8"))
    posed = copy.deepcopy(bb)
    for g in posed["groups"]:
        if g["name"] in pose:
            g["rotation"] = [g["rotation"][i] + pose[g["name"]][i] for i in range(3)]
    mesh = build_mesh(posed)
    tex = texture_array(bb)
    ours = render(mesh, tex, VIEWS["lado_direito"], size=600, background=None)
    shot = np.array(Image.open(os.path.join(shots_dir, "bb_pose_lado_direito.png")).convert("RGBA"))
    a, b = _mask(shot), _mask(ours)
    iou = round(float((a & b).sum() / max(1, (a | b).sum())), 4)
    ours_img = Image.fromarray(render(mesh, tex, VIEWS["lado_direito"], size=420,
                                      background=(255, 255, 255, 255))).convert("RGB")
    shot_img = Image.alpha_composite(Image.new("RGBA", (shot.shape[1], shot.shape[0]), (255, 255, 255, 255)),
                                     Image.fromarray(shot)).convert("RGB")
    arr = np.array(shot_img)
    ys, xs = np.nonzero((arr < 250).any(axis=2))
    crop = shot_img.crop((xs.min() - 20, ys.min() - 20, xs.max() + 20, ys.max() + 20))
    k = 420 / max(crop.size)
    crop = crop.resize((int(crop.width * k), int(crop.height * k)))
    row = Image.new("RGB", (840, 460), "white")
    row.paste(ours_img, (0, 40))
    row.paste(crop, (420 + (420 - crop.width) // 2, 40 + (420 - crop.height) // 2))
    d = ImageDraw.Draw(row)
    d.text((10, 8), "Pose de teste: prévia do Ninho", fill=(20, 20, 20), font=_font(17))
    d.text((430, 8), "Pose de teste: Blockbench 5.2.2", fill=(20, 20, 20), font=_font(17))
    row.save(out_png)
    return {"pose": pose, "iou_lado_direito": iou}


if __name__ == "__main__":
    # uso: compare_renders.py modelo.bbmodel pasta_capturas [lado_a_lado.png] [--pose pose.json saida.png]
    args = sys.argv[1:]
    pose_args = None
    if "--pose" in args:
        i = args.index("--pose")
        pose_args = args[i + 1:i + 3]
        args = args[:i]
    result = compare(args[0], args[1])
    if pose_args:
        result["pose"] = pose_compare(args[0], args[1], pose_args[0], pose_args[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if len(args) > 2:
        side_by_side(args[0], args[1], args[2])
