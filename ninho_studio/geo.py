"""Exportação da geometria para o GeckoLib (Minecraft Java): arquivo ``.geo.json``.

O GeckoLib lê a geometria no formato Bedrock (``format_version`` "1.12.0"). O plugin
oficial do GeckoLib para o Blockbench ("GeckoLib Models & Animations", JannisX11/
blockbench-plugins/plugins/geckolib) exporta com o próprio codec Bedrock do Blockbench
(``Codecs.bedrock.compile``); ele só remove ``item_display_transforms`` e força "1.12.0".

Este módulo traduz esse codec (``js/formats/bedrock/bedrock.js`` e ``compileJSON`` de
``js/util/json.ts``, Blockbench 5.2.2) para o subconjunto que o Ninho gera: cubos com
box UV dentro de grupos (ossos). A saída é comparada byte a byte com a exportação do
Blockbench nos testes (``examples/*/blockbench/*.geo.json``).

Convenções do codec Bedrock: X é espelhado (``pivot[0]`` e a origem dos cubos trocam de
sinal) e as rotações em X e Y trocam de sinal; Z fica igual.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any, Optional

import numpy as np

from .geometry import pivot_matrix, transform_points

GEO_FORMAT_VERSION = "1.12.0"

# Onde cada versão do GeckoLib procura os arquivos (conferido no código-fonte do GeckoLib):
#   GeckoLib 4 (Minecraft 1.20.1 a 1.21.4): GeckoLibCache lê as pastas "geo" e "animations".
#   GeckoLib 5 (Minecraft 1.21.5 em diante): GeckoLibResources lê "geckolib/models" e "geckolib/animations".
GECKOLIB_PATHS = {
    "geckolib4": {
        "minecraft": "1.20.1 a 1.21.4",
        "model": "assets/{modid}/geo/entity/{name}.geo.json",
        "animation": "assets/{modid}/animations/entity/{name}.animation.json",
        "texture": "assets/{modid}/textures/entity/{name}.png",
    },
    "geckolib5": {
        "minecraft": "1.21.5 em diante",
        "model": "assets/{modid}/geckolib/models/entity/{name}.geo.json",
        "animation": "assets/{modid}/geckolib/animations/entity/{name}.animation.json",
        "texture": "assets/{modid}/textures/entity/{name}.png",
    },
}


class OneLiner(dict):
    """Objeto escrito numa linha só, como ``oneLiner`` do Blockbench (usado nos cubos)."""


# ---------------------------------------------------------------------------
# JSON no estilo do Blockbench (compileJSON)
# ---------------------------------------------------------------------------

def _js_number(value: float) -> str:
    """``(Math.round(o*100000)/100000).toString()`` do JavaScript."""
    if isinstance(value, float) and math.isnan(value):
        return "null"
    v = math.floor(float(value) * 100000 + 0.5) / 100000  # Math.round arredonda .5 para cima
    if v == 0:
        return "0"  # também cobre -0
    if v.is_integer() and abs(v) < 1e21:
        return str(int(v))
    text = repr(v)
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    return text


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = re.sub(r"\n|\r\n", "\\\\n", text)
    return text.replace("\t", "\\t")


def compile_json(obj: Any, indentation: str = "\t", small: bool = False, final_newline: bool = False) -> str:
    """Tradução de ``compileJSON`` (Blockbench). Padrões do Blockbench: tabulação, sem quebra final."""

    def new_line(tabs: int) -> str:
        return "" if small else "\n" + indentation * tabs

    def handle(o: Any, tabs: int, breaks: bool = True) -> str:
        if isinstance(o, str):
            return '"' + _escape(o) + '"'
        if isinstance(o, bool):
            return "true" if o else "false"
        if o is None or (isinstance(o, float) and math.isinf(o)):
            return "null"
        if isinstance(o, (int, float)):
            return _js_number(o)
        if isinstance(o, (list, tuple)):
            multiline = any(isinstance(item, (dict, list, tuple)) or item is None for item in o)
            if not multiline:
                length = sum(len(item) + 4 if isinstance(item, str) else 3 for item in o)
                multiline = length > 140
            out, has_content = "[", False
            for item in o:
                compiled = handle(item, tabs + 1)
                if compiled:
                    if has_content:
                        out += "," + ("" if (small or multiline) else " ")
                    if multiline:
                        out += new_line(tabs)
                    out += compiled
                    has_content = True
            if multiline:
                out += new_line(tabs - 1)
            return out + "]"
        if isinstance(o, dict):
            breaks = breaks and not isinstance(o, OneLiner)
            out, has_content = "{", False
            for key, val in o.items():
                compiled = handle(val, tabs + 1, breaks)
                if compiled:
                    if has_content:
                        out += "," + ("" if (breaks or small) else " ")
                    if breaks:
                        out += new_line(tabs)
                    out += '"' + _escape(str(key)) + '":' + ("" if small else " ")
                    out += compiled
                    has_content = True
            if breaks and has_content:
                out += new_line(tabs - 1)
            return out + "}"
        raise TypeError(f"tipo não suportado no JSON: {type(o).__name__}")

    text = handle(obj, 1)
    return text + "\n" if final_newline else text


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------

def _all_zero(values: Any) -> bool:
    return all(float(v) == 0 for v in values)


def _exported_corners(bbmodel: dict[str, Any]) -> np.ndarray:
    """Os 8 cantos (no mundo, já com a pose dos ossos) de cada cubo exportado."""
    from .mesh import _adjusted_from_to

    groups = {g["uuid"]: g for g in bbmodel.get("groups", [])}
    parent_of: dict[str, Optional[str]] = {}

    def walk(nodes: list[Any], parent: Optional[str]) -> None:
        for node in nodes:
            if isinstance(node, str):
                parent_of[node] = parent
            else:
                parent_of[node["uuid"]] = parent
                walk(node.get("children", []), node["uuid"])

    walk(bbmodel.get("outliner", []), None)
    cache: dict[str, np.ndarray] = {}

    def gmat(uid: Optional[str]) -> np.ndarray:
        if uid is None:
            return np.eye(4)
        if uid not in cache:
            g = groups[uid]
            cache[uid] = gmat(parent_of.get(uid)) @ pivot_matrix(g.get("origin", [0, 0, 0]), g.get("rotation", [0, 0, 0]))
        return cache[uid]

    pts = []
    for el in bbmodel.get("elements", []):
        if el.get("type", "cube") != "cube" or not el.get("export", True):
            continue
        frm, to = _adjusted_from_to(el)
        corners = np.array([[x, y, z] for x in (frm[0], to[0]) for y in (frm[1], to[1]) for z in (frm[2], to[2])])
        m = gmat(parent_of.get(el["uuid"])) @ pivot_matrix(el.get("origin", [0, 0, 0]), el.get("rotation", [0, 0, 0]))
        pts.append(transform_points(m, corners))
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def calculate_visible_box(bbmodel: dict[str, Any]) -> list:
    """``calculateVisibleBox`` do Blockbench, partindo do ``visible_box`` guardado no projeto."""
    width, height, offset = (list(bbmodel.get("visible_box") or [1, 1, 0]) + [1, 1, 0])[:3]
    pts = _exported_corners(bbmodel)
    if len(pts):
        lo = pts.min(axis=0) + 8.0
        hi = pts.max(axis=0) + 8.0
        radius = max(hi[0], hi[2], -lo[0], -lo[2])
        y_lo, y_hi = math.floor(lo[1] / 16), math.ceil(hi[1] / 16)
    else:
        radius, y_lo, y_hi = 0.0, 0, 0
    w = max(math.ceil(radius * 2 / 16), width)
    y_lo = min(y_lo, offset - height / 2)
    y_hi = max(y_hi, offset + height / 2)
    return [w, y_hi - y_lo, (y_hi + y_lo) / 2]


def _compile_cube(el: dict[str, Any], bone: dict[str, Any]) -> dict[str, Any]:
    if not el.get("box_uv", True):
        raise ValueError(f"cubo {el.get('name')!r}: só box UV é exportado (o Ninho sempre gera box UV)")
    frm = [float(v) for v in el["from"]]
    to = [float(v) for v in el["to"]]
    size = [to[i] - frm[i] for i in range(3)]
    tpl = OneLiner(origin=frm[:], size=size)
    if el.get("inflate"):
        tpl["inflate"] = float(el["inflate"])
    tpl["origin"][0] = -(tpl["origin"][0] + size[0])
    rotation = [float(v) for v in el.get("rotation", [0, 0, 0])]
    if not _all_zero(rotation):
        pivot = [float(v) for v in el.get("origin", [0, 0, 0])]
        pivot[0] *= -1
        tpl["pivot"] = pivot
        tpl["rotation"] = [-rotation[0], -rotation[1], rotation[2]]
    tpl["uv"] = list(el.get("uv_offset", [0, 0]))
    mirror = bool(el.get("mirror_uv", False))
    if mirror == (not bone.get("mirror", False)):
        tpl["mirror"] = mirror
    return tpl


def bbmodel_to_geo(bbmodel: dict[str, Any]) -> dict[str, Any]:
    """Geometria Bedrock 1.12.0 (lida pelo GeckoLib), igual à ``Codecs.bedrock.compile()`` do Blockbench."""
    groups = {g["uuid"]: g for g in bbmodel.get("groups", [])}
    elements = {e["uuid"]: e for e in bbmodel.get("elements", [])}
    box_uv_project = bool(bbmodel.get("meta", {}).get("box_uv", True))
    res = bbmodel.get("resolution", {})
    description: dict[str, Any] = {
        "identifier": "geometry." + (bbmodel.get("model_identifier") or "unknown"),
        "texture_width": int(res.get("width") or 16),
        "texture_height": int(res.get("height") or 16),
    }

    bones: list[dict[str, Any]] = []

    def compile_group(node: dict[str, Any], parent: Optional[dict[str, Any]]) -> None:
        g = groups[node["uuid"]]
        children = node.get("children", [])
        if g.get("export", True) is False:
            raise ValueError(f"grupo {g.get('name')!r} marcado para não exportar (não suportado)")
        bone: dict[str, Any] = {"name": g["name"]}
        if parent is not None:
            bone["parent"] = parent["name"]
        pivot = [float(v) for v in g.get("origin", [0, 0, 0])]
        pivot[0] *= -1
        bone["pivot"] = pivot
        rotation = [float(v) for v in g.get("rotation", [0, 0, 0])]
        if not _all_zero(rotation):
            bone["rotation"] = [-rotation[0], -rotation[1], rotation[2]]
        if g.get("bedrock_binding"):
            bone["binding"] = g["bedrock_binding"]
        if g.get("reset"):
            bone["reset"] = True
        if g.get("mirror_uv") and box_uv_project:
            bone["mirror"] = True
        if g.get("material"):
            bone["material"] = g["material"]
        cubes = [_compile_cube(elements[c], bone) for c in children
                 if isinstance(c, str) and elements[c].get("export", True)]
        if cubes:
            bone["cubes"] = cubes
        bones.append(bone)
        for child in children:
            if isinstance(child, dict):
                compile_group(child, g)

    loose = [n for n in bbmodel.get("outliner", []) if isinstance(n, str)]
    if loose:
        raise ValueError("há cubos fora de qualquer osso; o Blockbench criaria o osso 'bb_main' (não suportado)")
    for node in bbmodel.get("outliner", []):
        compile_group(node, None)

    if bones:
        vb = calculate_visible_box(bbmodel)
        description["visible_bounds_width"] = vb[0] or 0
        description["visible_bounds_height"] = vb[1] or 0
        description["visible_bounds_offset"] = [0, vb[2] or 0, 0]
    entity: dict[str, Any] = {"description": description}
    if bones:
        entity["bones"] = bones
    return {"format_version": GEO_FORMAT_VERSION, "minecraft:geometry": [entity]}


def geo_dumps(geo: dict[str, Any]) -> str:
    """Texto do .geo.json exatamente como o Blockbench grava (tabulação, cubos em uma linha)."""
    return compile_json(geo)


# ---------------------------------------------------------------------------
# Conferência específica para o GeckoLib
# ---------------------------------------------------------------------------

def validate_geo(geo: dict[str, Any], texture_size: Optional[tuple[int, int]] = None) -> list[str]:
    """Problemas que impediriam o GeckoLib de carregar ou mapear a textura (lista vazia = ok).

    Baseado no leitor do GeckoLib 5 (``Geometry``/``GeometryBone``/``GeometryCube``) e 4
    (``FormatVersion``): versão 1.12.0, largura/altura da textura inteiras, nomes de ossos
    únicos, pais existentes e sem ciclos, tamanhos inteiros em box UV (o GeckoLib usa
    ``floor`` do tamanho para o UV) e UV dentro da textura.
    """
    problems: list[str] = []
    if geo.get("format_version") != GEO_FORMAT_VERSION:
        problems.append(f"format_version {geo.get('format_version')!r}: o GeckoLib 4 só aceita {GEO_FORMAT_VERSION}")
    defs = geo.get("minecraft:geometry")
    if not isinstance(defs, list) or len(defs) != 1:
        return problems + ["é esperado exatamente 1 item em minecraft:geometry"]
    desc = defs[0].get("description", {})
    tw, th = desc.get("texture_width"), desc.get("texture_height")
    if not (isinstance(tw, int) and isinstance(th, int) and tw > 0 and th > 0):
        problems.append("texture_width/texture_height ausentes ou não inteiros (o GeckoLib exige)")
        tw, th = 0, 0
    if texture_size is not None and (tw, th) != tuple(texture_size):
        problems.append(f"textura do modelo {tw}x{th} difere do PNG {texture_size[0]}x{texture_size[1]}")
    if not re.fullmatch(r"geometry\.[a-z0-9_.\-]+", str(desc.get("identifier", ""))):
        problems.append(f"identifier {desc.get('identifier')!r} fora do padrão geometry.<nome>")
    bones = defs[0].get("bones", [])
    names = [b.get("name") for b in bones]
    for n in sorted({n for n in names if names.count(n) > 1}, key=str):
        problems.append(f"osso {n!r} repetido (o GeckoLib identifica ossos pelo nome)")
    known = set(names)
    parent_of = {b.get("name"): b.get("parent") for b in bones}
    for b in bones:
        name, parent = b.get("name"), b.get("parent")
        if not name:
            problems.append("osso sem nome")
        if parent is not None and parent not in known:
            problems.append(f"osso {name!r}: pai {parent!r} não existe")
        seen, cur = set(), name
        while cur is not None and cur in parent_of:
            if cur in seen:
                problems.append(f"osso {name!r}: hierarquia em ciclo")
                break
            seen.add(cur)
            cur = parent_of[cur]
        for key in ("pivot", "rotation"):
            if key in b and not (len(b[key]) == 3 and all(math.isfinite(float(v)) for v in b[key])):
                problems.append(f"osso {name!r}: {key} inválido")
        for k, cube in enumerate(b.get("cubes", [])):
            label = f"osso {name!r}, cubo {k}"
            size, origin, uv = cube.get("size"), cube.get("origin"), cube.get("uv")
            if not (isinstance(size, list) and len(size) == 3 and isinstance(origin, list) and len(origin) == 3):
                problems.append(f"{label}: origin/size ausentes")
                continue
            if any(float(s) < 0 for s in size):
                problems.append(f"{label}: tamanho negativo {size}")
            if any(abs(float(s) - round(float(s))) > 1e-6 for s in size):
                problems.append(f"{label}: tamanho {size} não inteiro (o GeckoLib arredonda para baixo no box UV)")
            if not (isinstance(uv, list) and len(uv) == 2):
                problems.append(f"{label}: uv deve ser [u, v] (box UV)")
                continue
            w, h, d = (math.floor(float(s) + 1e-7) for s in size)
            u, v = float(uv[0]), float(uv[1])
            if tw and th and (u < 0 or v < 0 or u + 2 * (d + w) > tw or v + d + h > th):
                problems.append(f"{label}: UV {uv} com tamanho {size} sai da textura {tw}x{th}")
    return problems
