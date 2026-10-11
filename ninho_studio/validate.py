"""Validação do projeto exportado (.bbmodel + textura).

Trabalha sobre o dicionário .bbmodel (o que vai para o arquivo), não sobre o
modelo interno, para pegar qualquer erro de exportação. Verificações:

* cabeçalho (versão do formato, formato de projeto, box UV);
* dimensões inválidas (negativas, não finitas, degeneradas, não inteiras em box UV);
* identificadores (UUID) inválidos ou duplicados; nomes de ossos duplicados;
* referências inexistentes (outliner → grupos/cubos, faces → texturas);
* hierarquia quebrada (itens fora do outliner, repetidos ou cubos fora de ossos);
* UV fora da textura e UV inconsistente com o box UV;
* sobreposição de regiões no atlas e faces sem pintura (cubos "recortados", como os
  dentes, podem ter transparência de propósito);
* pivôs longe da geometria e partes abaixo do chão;
* faces de cubos diferentes no mesmo plano e viradas para o mesmo lado (piscam no jogo).
"""

from __future__ import annotations

import math
import re
import uuid as uuidlib
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .bbmodel import FORMAT_VERSION, MODEL_FORMAT, decode_data_url
from .coplanar import bbmodel_overlaps
from .geometry import pivot_matrix, transform_points
from .uv import FACES, box_uv_face_rects, rect_bounds

NAME_RE = re.compile(r"^[\w.\-]+$")


@dataclass
class Issue:
    level: str  # "erro" ou "aviso"
    code: str
    message: str

    def __str__(self) -> str:
        icon = "❌" if self.level == "erro" else "⚠️"
        return f"{icon} [{self.code}] {self.message}"


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "erro"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "aviso"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, message: str) -> None:
        self.issues.append(Issue("erro", code, message))

    def warn(self, code: str, message: str) -> None:
        self.issues.append(Issue("aviso", code, message))

    def summary_pt(self) -> str:
        head = "✅ Validação sem erros" if self.ok else f"❌ Validação encontrou {len(self.errors)} erro(s)"
        if self.warnings:
            head += f" e {len(self.warnings)} aviso(s)"
        lines = [head, f"Verificações: {len(self.checks)} ({', '.join(self.checks)})"]
        lines += [str(i) for i in self.issues]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [str(i) for i in self.errors],
            "warnings": [str(i) for i in self.warnings],
            "checks": self.checks,
            "stats": self.stats,
        }


def _finite_vec(v: Any, n: int = 3) -> bool:
    return (
        isinstance(v, list)
        and len(v) == n
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v)
    )


def _is_uuid(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    try:
        uuidlib.UUID(text)
        return True
    except ValueError:
        return False


def validate_bbmodel(
    bb: dict[str, Any],
    element_budget: Optional[int] = None,
    texture: Optional[np.ndarray] = None,
    ground_tolerance: float = 0.3,
    cutout: Optional[set[str]] = None,
) -> ValidationReport:
    """Valida o projeto. ``cutout``: UUIDs dos cubos com transparência de propósito (padrão: nomes "teeth*")."""
    rep = ValidationReport()

    # 1) cabeçalho -------------------------------------------------------------
    rep.checks.append("cabeçalho")
    meta = bb.get("meta", {})
    if meta.get("format_version") != FORMAT_VERSION:
        rep.error("formato", f"meta.format_version = {meta.get('format_version')!r}, esperado {FORMAT_VERSION!r}")
    if meta.get("model_format") != MODEL_FORMAT:
        rep.error("formato", f"meta.model_format = {meta.get('model_format')!r}, esperado {MODEL_FORMAT!r}")
    if meta.get("box_uv") is not True:
        rep.error("formato", "meta.box_uv deveria ser true")
    res = bb.get("resolution", {})
    W, H = res.get("width"), res.get("height")
    if not (isinstance(W, int) and isinstance(H, int) and W > 0 and H > 0):
        rep.error("resolucao", f"resolution inválida: {res}")
        W, H = 16, 16

    # 2) texturas ---------------------------------------------------------------
    rep.checks.append("texturas")
    textures = bb.get("textures", [])
    if len(textures) != 1:
        rep.warn("texturas", f"o formato Bedrock usa uma textura por modelo; encontradas {len(textures)}")
    tex_img = texture
    for k, tex in enumerate(textures):
        if tex.get("uv_width") != W or tex.get("uv_height") != H:
            rep.error("texturas", f"textura {k}: uv_width/uv_height {tex.get('uv_width')}x{tex.get('uv_height')} ≠ resolução {W}x{H}")
        try:
            data = decode_data_url(tex.get("source", ""))
            from io import BytesIO

            from PIL import Image

            img = Image.open(BytesIO(data))
            if img.format != "PNG":
                rep.error("texturas", f"textura {k} não é PNG")
            if img.size != (tex.get("width"), tex.get("height")):
                rep.error("texturas", f"textura {k}: tamanho do PNG {img.size} ≠ width/height {tex.get('width')}x{tex.get('height')}")
            if k == 0 and tex_img is None:
                tex_img = np.array(img.convert("RGBA"))
        except Exception as exc:  # noqa: BLE001
            rep.error("texturas", f"textura {k}: não foi possível decodificar ({exc})")

    # 3) UUIDs -------------------------------------------------------------------
    rep.checks.append("identificadores")
    elements = bb.get("elements", [])
    groups = bb.get("groups", [])
    all_ids: dict[str, str] = {}
    for kind, items in (("cubo", elements), ("grupo", groups), ("textura", textures)):
        for item in items:
            uid = item.get("uuid")
            if not _is_uuid(uid):
                rep.error("uuid", f"{kind} {item.get('name')!r} tem UUID inválido: {uid!r}")
                continue
            if uid in all_ids:
                rep.error("uuid", f"UUID duplicado {uid} ({all_ids[uid]} e {kind} {item.get('name')!r})")
            all_ids[uid] = f"{kind} {item.get('name')!r}"
    names = [g.get("name") for g in groups]
    dup_names = sorted({n for n in names if names.count(n) > 1})
    for n in dup_names:
        rep.error("nomes", f"nome de osso duplicado: {n!r} (o Bedrock exige nomes únicos)")
    for n in names:
        if not isinstance(n, str) or not n:
            rep.error("nomes", "osso sem nome")
        elif not NAME_RE.match(n):
            rep.warn("nomes", f"nome de osso {n!r} tem caracteres fora de [A-Za-z0-9_.-]")

    # 4) dimensões e UV ---------------------------------------------------------
    rep.checks.append("dimensões")
    rep.checks.append("UV dentro da textura")
    rep.checks.append("consistência box UV")
    for el in elements:
        name = el.get("name")
        if el.get("type", "cube") != "cube":
            rep.warn("tipo", f"elemento {name!r} do tipo {el.get('type')!r} não é verificado")
            continue
        frm, to = el.get("from"), el.get("to")
        if not (_finite_vec(frm) and _finite_vec(to)):
            rep.error("dimensoes", f"cubo {name!r}: from/to inválidos")
            continue
        size = [to[i] - frm[i] for i in range(3)]
        if any(s < 0 for s in size):
            rep.error("dimensoes", f"cubo {name!r}: tamanho negativo {size}")
        if sum(1 for s in size if s == 0) >= 2:
            rep.error("dimensoes", f"cubo {name!r}: degenerado (duas ou mais dimensões zero)")
        if el.get("box_uv") and any(abs(s - round(s)) > 1e-6 for s in size):
            rep.warn("dimensoes", f"cubo {name!r}: tamanho não inteiro {size} em box UV (o Blockbench arredonda para baixo)")
        if any(abs(c) > 512 for c in frm + to):
            rep.warn("dimensoes", f"cubo {name!r}: coordenadas muito grandes")
        for key in ("origin", "rotation"):
            if key in el and not _finite_vec(el[key]):
                rep.error("dimensoes", f"cubo {name!r}: {key} inválido")
        if "inflate" in el and not (isinstance(el["inflate"], (int, float)) and math.isfinite(el["inflate"])):
            rep.error("dimensoes", f"cubo {name!r}: inflate inválido")
        faces = el.get("faces", {})
        missing = [f for f in FACES if f not in faces]
        if missing:
            rep.error("faces", f"cubo {name!r}: faces ausentes {missing}")
        for face, fd in faces.items():
            uv = fd.get("uv")
            if not _finite_vec(uv, 4):
                rep.error("uv", f"cubo {name!r} face {face}: uv inválida")
                continue
            tex_ref = fd.get("texture")
            if tex_ref is not None and not (isinstance(tex_ref, int) and 0 <= tex_ref < len(textures)):
                rep.error("referencias", f"cubo {name!r} face {face}: textura {tex_ref!r} inexistente")
            u0, v0, u1, v1 = rect_bounds(uv)
            if u0 < 0 or v0 < 0 or u1 > W or v1 > H:
                rep.error("uv", f"cubo {name!r} face {face}: UV {uv} fora da textura {W}x{H}")
        if el.get("box_uv") and not missing:
            expected = box_uv_face_rects(frm, to, el.get("uv_offset", [0, 0]), bool(el.get("mirror_uv")))
            for face in FACES:
                got = faces[face].get("uv")
                if _finite_vec(got, 4) and any(abs(got[i] - expected[face][i]) > 1e-6 for i in range(4)):
                    rep.error("uv", f"cubo {name!r} face {face}: UV {got} difere do box UV esperado {expected[face]}")

    # 5) outliner / hierarquia ----------------------------------------------------
    rep.checks.append("hierarquia")
    group_by_uuid = {g.get("uuid"): g for g in groups}
    element_by_uuid = {e.get("uuid"): e for e in elements}
    seen_groups: dict[str, int] = {}
    seen_elements: dict[str, int] = {}
    parent_of_element: dict[str, Optional[str]] = {}
    parent_of_group: dict[str, Optional[str]] = {}
    depth_max = 0

    def walk(nodes: Any, parent: Optional[str], depth: int) -> None:
        nonlocal depth_max
        depth_max = max(depth_max, depth)
        if not isinstance(nodes, list):
            rep.error("hierarquia", "children/outliner deveria ser uma lista")
            return
        for node in nodes:
            if isinstance(node, str):
                if node not in element_by_uuid:
                    rep.error("referencias", f"outliner referencia cubo inexistente {node}")
                seen_elements[node] = seen_elements.get(node, 0) + 1
                parent_of_element[node] = parent
                if parent is None:
                    rep.warn("hierarquia", f"cubo {element_by_uuid.get(node, {}).get('name')!r} está fora de qualquer osso")
            elif isinstance(node, dict):
                uid = node.get("uuid")
                if uid not in group_by_uuid:
                    rep.error("referencias", f"outliner referencia grupo inexistente {uid}")
                seen_groups[uid] = seen_groups.get(uid, 0) + 1
                if seen_groups[uid] > 1:
                    rep.error("hierarquia", f"grupo {group_by_uuid.get(uid, {}).get('name')!r} aparece mais de uma vez (ciclo ou duplicação)")
                    continue
                parent_of_group[uid] = parent
                walk(node.get("children", []), uid, depth + 1)
            else:
                rep.error("hierarquia", f"nó inválido no outliner: {node!r}")

    walk(bb.get("outliner", []), None, 0)
    for uid, el in element_by_uuid.items():
        count = seen_elements.get(uid, 0)
        if count == 0:
            rep.error("hierarquia", f"cubo {el.get('name')!r} não está no outliner")
        elif count > 1:
            rep.error("hierarquia", f"cubo {el.get('name')!r} aparece {count} vezes no outliner")
    for uid, g in group_by_uuid.items():
        if uid not in seen_groups:
            rep.error("hierarquia", f"grupo {g.get('name')!r} não está no outliner")
        for key in ("origin", "rotation"):
            if not _finite_vec(g.get(key)):
                rep.error("dimensoes", f"grupo {g.get('name')!r}: {key} inválido")

    # 6) atlas: sobreposição e pintura ---------------------------------------------
    rep.checks.append("sobreposição no atlas")
    owner = np.full((H, W), -1, dtype=int)
    overlaps: set[tuple[str, str]] = set()
    for idx, el in enumerate(elements):
        for face, fd in el.get("faces", {}).items():
            if fd.get("texture") is None or not _finite_vec(fd.get("uv"), 4):
                continue
            u0, v0, u1, v1 = (int(round(x)) for x in rect_bounds(fd["uv"]))
            u0, v0 = max(u0, 0), max(v0, 0)
            u1, v1 = min(u1, W), min(v1, H)
            if u1 <= u0 or v1 <= v0:
                continue
            region = owner[v0:v1, u0:u1]
            others = set(np.unique(region[(region >= 0) & (region != idx)]).tolist())
            for o in others:
                overlaps.add(tuple(sorted((elements[o].get("name"), el.get("name")))))
            region[region < 0] = idx
    for a, b in sorted(overlaps):
        rep.warn("atlas", f"regiões de UV sobrepostas entre {a!r} e {b!r}")
    used = int((owner >= 0).sum())
    rep.stats["atlas_usado_px"] = used
    rep.stats["atlas_ocupacao"] = round(used / float(W * H), 3)

    if tex_img is not None:
        rep.checks.append("pintura das faces")
        th, tw = tex_img.shape[:2]
        su, sv = tw / float(W), th / float(H)
        unpainted = 0
        if cutout is None:
            cutout = {el.get("uuid") for el in elements if str(el.get("name", "")).startswith("teeth")}
        for el in elements:
            is_cutout = el.get("uuid") in cutout
            visible = 0
            for face, fd in el.get("faces", {}).items():
                if fd.get("texture") is None or not _finite_vec(fd.get("uv"), 4):
                    continue
                u0, v0, u1, v1 = rect_bounds(fd["uv"])
                a0, a1 = int(round(u0 * su)), int(round(u1 * su))
                b0, b1 = int(round(v0 * sv)), int(round(v1 * sv))
                if a1 <= a0 or b1 <= b0:
                    continue
                alpha = tex_img[max(b0, 0):b1, max(a0, 0):a1, 3]
                if alpha.size == 0:
                    continue
                frac = float((alpha > 0).mean())
                visible += int((alpha > 0).sum())
                if is_cutout:
                    continue
                if frac == 0:
                    unpainted += 1
                    rep.error("pintura", f"cubo {el.get('name')!r} face {face}: região totalmente transparente")
                elif frac < 0.99:
                    rep.warn("pintura", f"cubo {el.get('name')!r} face {face}: {100 * (1 - frac):.0f}% transparente")
            if is_cutout and visible == 0:
                unpainted += 1
                rep.error("pintura", f"cubo recortado {el.get('name')!r}: nenhum pixel visível")
        rep.stats["faces_sem_pintura"] = unpainted
        rep.stats["cubos_recortados"] = sorted(el.get("name") for el in elements if el.get("uuid") in cutout)

    # 7) pivôs e chão (pose final) -------------------------------------------------
    rep.checks.append("pivôs")
    rep.checks.append("chão")
    gmats: dict[str, np.ndarray] = {}

    def gmat(uid: Optional[str]) -> np.ndarray:
        if uid is None:
            return np.eye(4)
        if uid not in gmats:
            g = group_by_uuid[uid]
            gmats[uid] = gmat(parent_of_group.get(uid)) @ pivot_matrix(g.get("origin", [0, 0, 0]), g.get("rotation", [0, 0, 0]))
        return gmats[uid]

    world_min_y = math.inf
    cubes_of_group: dict[str, list[dict[str, Any]]] = {}
    for uid, el in element_by_uuid.items():
        if not (_finite_vec(el.get("from")) and _finite_vec(el.get("to"))):
            continue
        parent = parent_of_element.get(uid)
        if parent is not None and parent in group_by_uuid:
            cubes_of_group.setdefault(parent, []).append(el)
        try:
            m = gmat(parent if parent in group_by_uuid else None) @ pivot_matrix(el.get("origin", [0, 0, 0]), el.get("rotation", [0, 0, 0]))
        except (KeyError, RecursionError):
            continue
        f, t = el["from"], el["to"]
        corners = np.array([[x, y, z] for x in (f[0], t[0]) for y in (f[1], t[1]) for z in (f[2], t[2])], dtype=float)
        world_min_y = min(world_min_y, float(transform_points(m, corners)[:, 1].min()))
    if math.isfinite(world_min_y):
        rep.stats["altura_minima"] = round(world_min_y, 3)
        if world_min_y < -ground_tolerance:
            rep.warn("chao", f"parte do modelo fica {abs(world_min_y):.2f} px abaixo do chão (Y=0)")
        elif world_min_y > ground_tolerance:
            rep.warn("chao", f"o modelo flutua {world_min_y:.2f} px acima do chão (Y=0)")
    for uid, cubes in cubes_of_group.items():
        g = group_by_uuid[uid]
        pts = np.array([c["from"] for c in cubes] + [c["to"] for c in cubes], dtype=float)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        margin = 3.0 + 0.25 * (hi - lo)
        o = np.array(g.get("origin", [0, 0, 0]), dtype=float)
        if np.any(o < lo - margin) or np.any(o > hi + margin):
            rep.warn("pivo", f"pivô do osso {g.get('name')!r} ({o.tolist()}) está longe dos próprios cubos")

    # 8) faces no mesmo plano (z-fighting) -----------------------------------------------
    rep.checks.append("faces no mesmo plano")
    try:
        coincident = bbmodel_overlaps(bb)
    except (KeyError, ValueError, np.linalg.LinAlgError):
        coincident = []
    for a, fa, b, fb, area in coincident:
        rep.warn("coplanar", f"faces coincidentes: {a!r} ({fa}) e {b!r} ({fb}), {area:.1f} px² — podem piscar no jogo")
    rep.stats["faces_coincidentes"] = len(coincident)

    # 9) orçamento ---------------------------------------------------------------------
    rep.checks.append("orçamento de elementos")
    rep.stats["cubos"] = len(elements)
    rep.stats["ossos"] = len(groups)
    rep.stats["profundidade_hierarquia"] = depth_max
    if element_budget is not None and len(elements) > element_budget:
        rep.error("orcamento", f"{len(elements)} cubos excedem o orçamento de {element_budget}")
    return rep
