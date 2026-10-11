"""Exportação/leitura do projeto editável do Blockbench (.bbmodel).

Versão do formato: ``meta.format_version = "5.0"`` (constante ``FORMATV`` em
``js/formats/bbmodel.js`` do Blockbench 5.2.2, a versão atual quando este
código foi escrito) e formato de projeto ``"bedrock"`` (Bedrock Entity:
ossos com pivô, box UV, uma textura por modelo).

Os campos gravados são os mesmos que o Blockbench 5.2.2 grava ao salvar um
projeto Bedrock equivalente (conferido gerando um projeto de referência no
próprio Blockbench; ver ``docs/FORMATO-BBMODEL.md``). Campos de estado da
interface (seleção) não são gravados.

O .bbmodel é o projeto EDITÁVEL. Para usar no Minecraft, abra-o no Blockbench
e exporte no formato do destino (ex.: File > Export > Export Bedrock Geometry;
GeckoLib e Java ficam para uma etapa posterior).
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
from typing import Any, Optional

import numpy as np

from .geometry import clean_number
from .model import Model
from .uv import FACES, box_uv_face_rects

FORMAT_VERSION = "5.0"
MODEL_FORMAT = "bedrock"
BLOCKBENCH_REFERENCE_VERSION = "5.2.2"

REGION_COLORS = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}


def sanitize_identifier(name: str) -> str:
    """Identificador seguro para Bedrock (``geometry.<id>``): minúsculas, dígitos, ``_`` e ``.``."""
    import unicodedata

    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9_.]+", "_", text).strip("_.")
    return text or "ninho_model"


def png_bytes(rgba: np.ndarray) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def png_data_url(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def decode_data_url(url: str) -> bytes:
    if not url.startswith("data:image/png;base64,"):
        raise ValueError("a textura não está embutida como PNG em base64")
    return base64.b64decode(url.split(",", 1)[1])


def _vec(v) -> list:
    return [clean_number(x) for x in v]


def compute_visible_box(model: Model) -> list:
    """Mesmo cálculo de ``calculateVisibleBox`` (js/formats/bedrock/bedrock.js), a partir de [1, 1, 0]."""
    lo, hi = model.world_bounds()
    lo = lo + 8.0
    hi = hi + 8.0
    radius = max(hi[0], hi[2], -lo[0], -lo[2])
    width = max(int(math.ceil(radius * 2 / 16.0)), 1)
    y_min = math.floor(lo[1] / 16.0)
    y_max = math.ceil(hi[1] / 16.0)
    y_min = min(y_min, 0 - 1 / 2)
    y_max = max(y_max, 0 + 1 / 2)
    return [clean_number(width), clean_number(y_max - y_min), clean_number((y_max + y_min) / 2)]


def model_to_bbmodel(model: Model, texture_png: bytes, texture_name: str, identifier: Optional[str] = None) -> dict[str, Any]:
    """Converte o modelo interno + PNG para o dicionário .bbmodel (formato 5.0, bedrock)."""
    if any(not b.uuid for b in model.bones.values()):
        raise ValueError("chame model.assign_uuids(seed) antes de exportar")
    ident = sanitize_identifier(identifier or model.name)
    elements = []
    for bone in model.bones.values():
        for cube in bone.cubes:
            region = int(cube.tags.get("region", 1))
            el: dict[str, Any] = {
                "name": cube.name,
                "box_uv": True,
                "render_order": "default",
                "locked": False,
                "export": True,
                "scope": 0,
                "allow_mirror_modeling": True,
                "from": _vec(cube.frm),
                "to": _vec(cube.to),
                "autouv": 0,
                "color": REGION_COLORS.get(region, 0),
            }
            if cube.mirror_uv:
                el["mirror_uv"] = True
            if cube.inflate:
                el["inflate"] = clean_number(cube.inflate)
            if any(abs(r) > 1e-9 for r in cube.rotation):
                el["rotation"] = _vec(cube.rotation)
            el["origin"] = _vec(cube.origin)
            if any(cube.uv_offset):
                el["uv_offset"] = [int(cube.uv_offset[0]), int(cube.uv_offset[1])]
            rects = box_uv_face_rects(cube.frm, cube.to, cube.uv_offset, cube.mirror_uv)
            el["faces"] = {face: {"uv": _vec(rects[face]), "texture": 0} for face in FACES}
            el["type"] = "cube"
            el["uuid"] = cube.uuid
            elements.append(el)

    groups = []
    for bone in model.bones.values():
        cubes = bone.cubes
        region = int(cubes[0].tags.get("region", 1)) if cubes else 1
        groups.append({
            "name": bone.name,
            "uuid": bone.uuid,
            "export": True,
            "locked": False,
            "scope": 0,
            "visibility": True,
            "origin": _vec(bone.pivot),
            "rotation": _vec(tuple(round(r, 3) for r in bone.rotation)),
            "bedrock_binding": "",
            "color": REGION_COLORS.get(region, 0),
            "children": [],
            "reset": False,
            "shade": True,
            "mirror_uv": False,
            "autouv": 0,
            "isOpen": bone.parent is None or bone.name in ("body",),
        })

    def outline(bone_name: str) -> dict[str, Any]:
        bone = model.bones[bone_name]
        children: list[Any] = [c.uuid for c in bone.cubes]
        children += [outline(child.name) for child in model.children(bone_name)]
        return {"uuid": bone.uuid, "isOpen": bone.parent is None or bone.name in ("body",), "children": children}

    outliner = [outline(b.name) for b in model.roots()]

    from PIL import Image

    img = Image.open(io.BytesIO(texture_png))
    tex_w, tex_h = img.size
    textures = [{
        "name": texture_name,
        "path": "",
        "folder": "",
        "namespace": "",
        "id": "0",
        "group": "",
        "scope": 0,
        "width": tex_w,
        "height": tex_h,
        "uv_width": model.texture_width,
        "uv_height": model.texture_height,
        "particle": False,
        "use_as_default": False,
        "layers_enabled": False,
        "sync_to_project": "",
        "file_format": "png",
        "render_mode": "default",
        "render_sides": "auto",
        "wrap_mode": "limited",
        "pbr_channel": "color",
        "fps": 7,
        "force_translucent": False,
        "frame_time": 1,
        "frame_order_type": "loop",
        "frame_order": "",
        "frame_interpolate": False,
        "visible": True,
        "internal": True,
        "saved": False,
        "uuid": _texture_uuid(model),
        "source": png_data_url(texture_png),
    }]

    return {
        "meta": {"format_version": FORMAT_VERSION, "model_format": MODEL_FORMAT, "box_uv": True},
        "name": model.name,
        "model_identifier": ident,
        "visible_box": compute_visible_box(model),
        "variable_placeholders": "",
        "multi_file_ruleset": "",
        "variable_placeholder_buttons": [],
        "bedrock_animation_mode": "entity",
        "timeline_setups": [],
        "unhandled_root_fields": {},
        "resolution": {"width": model.texture_width, "height": model.texture_height},
        "elements": elements,
        "groups": groups,
        "outliner": outliner,
        "textures": textures,
    }


def _texture_uuid(model: Model) -> str:
    import uuid as uuidlib

    from .model import NINHO_UUID_NAMESPACE

    seed_part = model.meta.get("seed", 0)
    return str(uuidlib.uuid5(NINHO_UUID_NAMESPACE, f"{seed_part}/texture/{model.name}"))


def dumps(bbmodel: dict[str, Any]) -> str:
    """JSON com tabulação, como o Blockbench grava por padrão."""
    return json.dumps(bbmodel, ensure_ascii=False, indent="\t") + "\n"


def loads(text: str) -> dict[str, Any]:
    return json.loads(text)


def texture_array(bbmodel: dict[str, Any], index: int = 0) -> np.ndarray:
    from PIL import Image

    data = decode_data_url(bbmodel["textures"][index]["source"])
    return np.array(Image.open(io.BytesIO(data)).convert("RGBA"))
