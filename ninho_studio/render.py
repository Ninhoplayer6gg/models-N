"""Renderizador por software (numpy) para prévias dentro do notebook.

Funciona sem GPU e sem bibliotecas gráficas extras: rasteriza os triângulos
da malha lida do .bbmodel com z-buffer, amostragem de textura "nearest"
(pixels nítidos), teste de alfa e iluminação simples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .mesh import Mesh

LIGHT_MAIN = np.array([0.45, 1.0, -0.6])
LIGHT_MAIN = LIGHT_MAIN / np.linalg.norm(LIGHT_MAIN)
LIGHT_FILL = np.array([-0.6, 0.3, 0.7])
LIGHT_FILL = LIGHT_FILL / np.linalg.norm(LIGHT_FILL)


@dataclass
class View:
    name: str
    direction: tuple[float, float, float]  # do alvo para a câmera
    ortho: bool = True
    up: tuple[float, float, float] = (0.0, 1.0, 0.0)
    fov: float = 30.0


# A criatura olha para -Z (norte); o lado direito do animal fica em +X.
VIEWS = {
    "perspectiva": View("Perspectiva 3/4", (0.75, 0.5, -0.9), ortho=False),
    "lado_direito": View("Lado direito", (1.0, 0.0, 0.0)),
    "frente": View("Frente", (0.0, 0.0, -1.0)),
    "topo": View("Topo", (0.0, 1.0, 0.0), up=(-1.0, 0.0, 0.0)),
    "traseira": View("Traseira 3/4", (-0.8, 0.45, 0.9), ortho=False),
    "baixo": View("Baixo (ventre)", (0.0, -1.0, 0.0), up=(-1.0, 0.0, 0.0)),
    "lado_esquerdo": View("Lado esquerdo", (-1.0, 0.0, 0.0)),
}


def _basis(direction: Sequence[float], up: Sequence[float]) -> np.ndarray:
    f = -np.asarray(direction, dtype=float)
    f /= np.linalg.norm(f)  # para onde a câmera olha
    upv = np.asarray(up, dtype=float)
    r = np.cross(f, upv)
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(f, np.array([0.0, 0.0, 1.0]))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return np.stack([r, u, f])  # linhas: direita, cima, frente


def _font(size: int):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antigo
        return ImageFont.load_default()


def render(
    mesh: Mesh,
    texture: np.ndarray,
    view: View,
    size: int = 480,
    margin: float = 0.08,
    background: Optional[Sequence[int]] = (238, 240, 236, 255),
    shading: bool = True,
    return_projection: bool = False,
):
    """Renderiza a malha e devolve uma imagem RGBA (numpy uint8)."""
    W = H = int(size)
    tex = texture.astype(np.float32)
    th, tw = texture.shape[:2]
    su = tw / float(mesh.uv_size[0])
    sv = th / float(mesh.uv_size[1])

    lo, hi = mesh.bounds
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2 or 1.0
    basis = _basis(view.direction, view.up)
    pts = mesh.positions.reshape(-1, 3) - center
    cam = pts @ basis.T  # x direita, y cima, z frente (profundidade)
    if view.ortho:
        depth = cam[:, 2]
        sx, sy = cam[:, 0], cam[:, 1]
        inv_w = np.ones_like(depth)
    else:
        dist = radius / math.sin(math.radians(view.fov) / 2) * 1.05
        depth = cam[:, 2] + dist
        sx = cam[:, 0] / depth
        sy = cam[:, 1] / depth
        inv_w = 1.0 / depth
    # enquadramento automático
    x0, x1 = sx.min(), sx.max()
    y0, y1 = sy.min(), sy.max()
    span = max(x1 - x0, y1 - y0) or 1.0
    scale = (1 - 2 * margin) * W / span
    px = (sx - (x0 + x1) / 2) * scale + W / 2
    py = H / 2 - (sy - (y0 + y1) / 2) * scale

    T = len(mesh.positions)
    px = px.reshape(T, 3)
    py = py.reshape(T, 3)
    dz = depth.reshape(T, 3)
    iw = inv_w.reshape(T, 3)

    color = np.zeros((H, W, 3), dtype=np.float32)
    alpha = np.zeros((H, W), dtype=bool)
    zbuf = np.full((H, W), np.inf, dtype=np.float64)

    dir_unit = np.asarray(view.direction, dtype=float)
    dir_unit = dir_unit / np.linalg.norm(dir_unit)
    cam_pos = center + dir_unit * (radius / math.sin(math.radians(view.fov) / 2) * 1.05)
    for t in range(T):
        n = mesh.normals[t]
        # descarta faces de costas para a câmera (cubos fechados)
        if view.ortho:
            if np.dot(n, dir_unit) <= 1e-6:
                continue
        elif np.dot(n, cam_pos - mesh.positions[t, 0]) <= 1e-6:
            continue
        xs, ys = px[t], py[t]
        minx = max(int(math.floor(xs.min())), 0)
        maxx = min(int(math.ceil(xs.max())), W - 1)
        miny = max(int(math.floor(ys.min())), 0)
        maxy = min(int(math.ceil(ys.max())), H - 1)
        if minx > maxx or miny > maxy:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        x0_, y0_ = xs[0], ys[0]
        x1_, y1_ = xs[1], ys[1]
        x2_, y2_ = xs[2], ys[2]
        area = (x1_ - x0_) * (y2_ - y0_) - (x2_ - x0_) * (y1_ - y0_)
        if abs(area) < 1e-12:
            continue
        w0 = ((x1_ - gx) * (y2_ - gy) - (x2_ - gx) * (y1_ - gy)) / area
        w1 = ((x2_ - gx) * (y0_ - gy) - (x0_ - gx) * (y2_ - gy)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-7) & (w1 >= -1e-7) & (w2 >= -1e-7)
        if not inside.any():
            continue
        # interpolação com correção de perspectiva
        iw_t = iw[t]
        denom = w0 * iw_t[0] + w1 * iw_t[1] + w2 * iw_t[2]
        z = (w0 * dz[t, 0] * iw_t[0] + w1 * dz[t, 1] * iw_t[1] + w2 * dz[t, 2] * iw_t[2]) / denom
        uvt = mesh.uvs[t]
        u = (w0 * uvt[0, 0] * iw_t[0] + w1 * uvt[1, 0] * iw_t[1] + w2 * uvt[2, 0] * iw_t[2]) / denom
        v = (w0 * uvt[0, 1] * iw_t[0] + w1 * uvt[1, 1] * iw_t[1] + w2 * uvt[2, 1] * iw_t[2]) / denom
        rect = mesh.uv_rects[t]
        u = np.clip(u, rect[0] + 1e-4, rect[2] - 1e-4)
        v = np.clip(v, rect[1] + 1e-4, rect[3] - 1e-4)
        tx = np.clip((u * su).astype(int), 0, tw - 1)
        ty = np.clip((v * sv).astype(int), 0, th - 1)
        texel = tex[ty, tx]
        ok = inside & (texel[..., 3] >= 128)
        sub_z = zbuf[miny:maxy + 1, minx:maxx + 1]
        closer = ok & (z < sub_z)
        if not closer.any():
            continue
        if shading:
            light = 0.58 + 0.42 * max(0.0, float(np.dot(n, LIGHT_MAIN))) + 0.12 * max(0.0, float(np.dot(n, LIGHT_FILL)))
            light = min(light, 1.0)
        else:
            light = 1.0
        sub_c = color[miny:maxy + 1, minx:maxx + 1]
        sub_c[closer] = texel[..., :3][closer] * light
        sub_z[closer] = z[closer]
        alpha[miny:maxy + 1, minx:maxx + 1] |= closer

    out = np.zeros((H, W, 4), dtype=np.uint8)
    if background is not None:
        out[:] = np.array(background, dtype=np.uint8)
    out[alpha, :3] = np.clip(color[alpha], 0, 255).astype(np.uint8)
    out[alpha, 3] = 255
    if return_projection:
        def project(p: np.ndarray) -> np.ndarray:
            c = (np.atleast_2d(p) - center) @ basis.T
            if view.ortho:
                qx, qy = c[:, 0], c[:, 1]
            else:
                dist = radius / math.sin(math.radians(view.fov) / 2) * 1.05
                d = c[:, 2] + dist
                qx, qy = c[:, 0] / d, c[:, 1] / d
            return np.stack([(qx - (x0 + x1) / 2) * scale + W / 2, H / 2 - (qy - (y0 + y1) / 2) * scale], axis=1)

        return out, project
    return out


def _label(img: Image.Image, text: str, size: int = 18) -> Image.Image:
    font = _font(size)
    pad = size // 2
    bar = Image.new("RGBA", (img.width, size + pad * 2), (40, 44, 52, 255))
    d = ImageDraw.Draw(bar)
    d.text((pad, pad - 2), text, fill=(245, 245, 245, 255), font=font)
    out = Image.new("RGBA", (img.width, img.height + bar.height), (255, 255, 255, 255))
    out.paste(bar, (0, 0))
    out.paste(img, (0, bar.height))
    return out


def contact_sheet(mesh: Mesh, texture: np.ndarray, views: Sequence[str] = ("perspectiva", "lado_direito", "frente", "topo", "traseira", "baixo"),
                  cell: int = 420, columns: int = 3, title: Optional[str] = None) -> Image.Image:
    tiles = []
    for key in views:
        v = VIEWS[key]
        arr = render(mesh, texture, v, size=cell)
        tiles.append(_label(Image.fromarray(arr), v.name))
    rows = math.ceil(len(tiles) / columns)
    tw, th = tiles[0].size
    head = 0
    if title:
        head = 44
    sheet = Image.new("RGBA", (tw * columns, th * rows + head), (255, 255, 255, 255))
    if title:
        d = ImageDraw.Draw(sheet)
        d.text((14, 10), title, fill=(30, 30, 30, 255), font=_font(22))
    for k, tile in enumerate(tiles):
        sheet.paste(tile, ((k % columns) * tw, head + (k // columns) * th))
    return sheet


def atlas_debug(bbmodel: dict, texture: np.ndarray, zoom: int = 4, labels: bool = True) -> Image.Image:
    """Textura ampliada com o contorno de cada face e o nome de cada cubo."""
    from .uv import rect_bounds

    th, tw = texture.shape[:2]
    res = bbmodel["resolution"]
    su = tw / float(res["width"])
    sv = th / float(res["height"])
    checker = np.indices((th, tw)).sum(axis=0) % 2
    bg = np.where(checker[..., None] == 0, 205, 230).astype(np.uint8).repeat(3, axis=2)
    rgb = texture[..., :3].astype(float)
    a = texture[..., 3:4].astype(float) / 255.0
    comp = (rgb * a + bg * (1 - a)).astype(np.uint8)
    img = Image.fromarray(comp).resize((tw * zoom, th * zoom), Image.NEAREST).convert("RGBA")
    d = ImageDraw.Draw(img)
    font = _font(max(9, zoom * 3))
    small = _font(max(8, zoom * 2 + 1))
    letters = {"north": "N", "south": "S", "east": "L", "west": "O", "up": "C", "down": "B"}
    for el in bbmodel["elements"]:
        boxes = []
        for face, fd in el["faces"].items():
            u0, v0, u1, v1 = rect_bounds(fd["uv"])
            if u1 - u0 <= 0 or v1 - v0 <= 0:
                continue
            box = (u0 * su * zoom, v0 * sv * zoom, u1 * su * zoom - 1, v1 * sv * zoom - 1)
            boxes.append(box)
            d.rectangle(box, outline=(255, 255, 255, 170), width=1)
            if labels and (u1 - u0) * zoom >= 10 and (v1 - v0) * zoom >= 10:
                d.text((box[0] + 2, box[1] + 1), letters[face], fill=(255, 255, 255, 230), font=small)
        if boxes:
            x0 = min(b[0] for b in boxes)
            y0 = min(b[1] for b in boxes)
            x1 = max(b[2] for b in boxes)
            y1 = max(b[3] for b in boxes)
            d.rectangle((x0, y0, x1, y1), outline=(20, 20, 20, 255), width=1)
            if labels:
                d.text((x0 + 2, y1 - zoom * 3 - 2), el["name"], fill=(255, 255, 0, 255), font=font, stroke_width=1, stroke_fill=(0, 0, 0, 255))
    return img


def skeleton_sheet(mesh: Mesh, texture: np.ndarray, size: int = 520) -> Image.Image:
    """Vistas lateral e superior com pivôs e ligações entre ossos (para conferir articulações)."""
    tiles = []
    for key in ("lado_direito", "topo"):
        v = VIEWS[key]
        arr, project = render(mesh, texture, v, size=size, return_projection=True)
        base = Image.fromarray(arr).convert("RGBA")
        veil = Image.new("RGBA", base.size, (255, 255, 255, 120))
        base = Image.alpha_composite(base, veil)
        d = ImageDraw.Draw(base)
        font = _font(12)
        names = list(mesh.bones)
        pos = {n: project(mesh.bones[n].pivot_world)[0] for n in names}
        for n in names:
            parent = mesh.bones[n].parent
            if parent and parent in pos:
                d.line([tuple(pos[parent]), tuple(pos[n])], fill=(30, 90, 200, 255), width=2)
        for n in names:
            x, y = pos[n]
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(220, 40, 40, 255), outline=(0, 0, 0, 255))
        if key == "lado_direito":
            # rotula só o lado direito e o eixo central (o lado esquerdo fica atrás)
            boxes: list[tuple[float, float, float, float]] = []
            offsets = [(6, -16), (6, 4), (-6, -16), (-6, 4), (6, -28), (6, 16), (-6, -28), (-6, 16)]
            for n in names:
                if n.endswith("_left") or n == "root":
                    continue
                x, y = pos[n]
                tw = d.textlength(n, font=font)
                for ox, oy in offsets:
                    lx = x + ox if ox > 0 else x + ox - tw
                    ly = y + oy
                    box = (lx - 1, ly - 1, lx + tw + 1, ly + 13)
                    clash = any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in boxes)
                    if not clash and 0 <= lx and lx + tw < base.width and ly >= 0:
                        break
                boxes.append(box)
                d.rectangle(box, fill=(255, 255, 255, 200))
                d.text((lx, ly), n, fill=(10, 10, 10, 255), font=font)
        tiles.append(_label(base, f"Esqueleto – {v.name}"))
    w = sum(t.width for t in tiles)
    h = max(t.height for t in tiles)
    sheet = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width
    return sheet
