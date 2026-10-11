"""Carrega os .geo.json do Ninho com os LEITORES DO GECKOLIB 4 E 5 (código-fonte original) e confere.

Não há Minecraft aqui, então o teste compila só a parte do GeckoLib que lê e "assa" a geometria,
sem alterações (GeckoLib 5: ``com.geckolib.loading.definition.geometry``, ``util.JsonUtil``,
``cache.model.GeoQuad/GeoVertex/ModelProperties``; GeckoLib 4: ``loading.json.raw``,
``loading.object.BakedModelFactory/GeometryTree``, ``cache.object``, ``util.JsonUtil``), junto com
substitutos mínimos das classes do Minecraft (``tools/geckolib_check/stubs``: Vec3, Direction,
GsonHelper...). Em seguida, para cada canto de cada
face, compara a posição e o UV calculados pelo GeckoLib com os do Blockbench (``ninho_studio.uv``,
tradução de ``Cube.updateUV``/``UVToLocal`` já conferida no Blockbench). Também confere ossos (pai,
pivô, rotação), cubos (tamanho, pivô, rotação) e o log do GeckoLib (avisos/erros).

O que este teste NÃO cobre: a renderização no jogo (matrizes de pose do GeckoLib, iluminação), o
registro da criatura e as animações — isso só um mod rodando no Minecraft mostra.

Uso:
    python tools/geckolib_loader_check.py --lib PASTA_DOS_JARS [--geckolib5 CHECKOUT] [--geckolib4 CHECKOUT]

PASTA_DOS_JARS precisa ter: gson (2.11+), guava, fastutil, jspecify, org.jetbrains annotations e joml
(todos do Maven Central). Sem ``--geckolib5``/``--geckolib4``, o GeckoLib é baixado do GitHub nos
commits testados. Resultado: docs/verificacao-geckolib-leitor.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from verify_geckolib import all_cases  # noqa: E402

from ninho_studio import __version__  # noqa: E402
from ninho_studio.mesh import _adjusted_from_to  # noqa: E402
from ninho_studio.uv import box_uv_face_rects, uv_to_local  # noqa: E402

GECKOLIB_REPO = "https://github.com/bernie-g/geckolib.git"
HERE = os.path.join(ROOT, "tools", "geckolib_check")
VERSIONS = {
    "geckolib5": {
        "label": "GeckoLib 5.5.7 (branch main, Minecraft 26.3; a família 5 cobre o Minecraft 1.21.5 em diante)",
        "commit": "7c96bef7e1658e4158453c17eb464f0fb7f92426",
        "sources": [
            "com/geckolib/loading/definition/geometry/*.java",
            "com/geckolib/loading/definition/geometry/object/*.java",
            "com/geckolib/util/JsonUtil.java",
            "com/geckolib/cache/model/GeoQuad.java",
            "com/geckolib/cache/model/GeoVertex.java",
            "com/geckolib/cache/model/ModelProperties.java",
        ],
        "stubs": ["minecraft", "geckolib5"],
        "main": "GeckoLibLoadCheck",
        # O GeckoLib 5 usa variáveis sem nome ("_"), estáveis a partir do Java 22 (prévia no 21).
        "javac": ["--release", "21", "--enable-preview"],
        "java": ["--enable-preview"],
    },
    "geckolib4": {
        "label": "GeckoLib 4.9.3 (branch 1.21.1; a família 4 cobre o Minecraft 1.20.1 a 1.21.4)",
        "commit": "cce098097cdd2084d8383bec593e0db79e0ed5a0",
        "sources": [
            "software/bernie/geckolib/loading/json/FormatVersion.java",
            "software/bernie/geckolib/loading/json/raw/*.java",
            "software/bernie/geckolib/loading/object/BakedModelFactory.java",
            "software/bernie/geckolib/loading/object/BoneStructure.java",
            "software/bernie/geckolib/loading/object/GeometryTree.java",
            "software/bernie/geckolib/cache/object/*.java",
            "software/bernie/geckolib/animation/state/BoneSnapshot.java",
            "software/bernie/geckolib/util/JsonUtil.java",
        ],
        "stubs": ["minecraft", "geckolib4"],
        "main": "GeckoLib4LoadCheck",
        "javac": ["--release", "21"],
        "java": [],
    },
}


def fetch_geckolib(dest: str, commit: str) -> str:
    subprocess.run(["git", "init", "-q", dest], check=True)
    subprocess.run(["git", "-C", dest, "fetch", "-q", "--depth", "1", GECKOLIB_REPO, commit], check=True)
    subprocess.run(["git", "-C", dest, "checkout", "-q", "FETCH_HEAD"], check=True)
    return dest


def build(version: str, geckolib: str, lib: str, work: str) -> str:
    cfg = VERSIONS[version]
    src_root = os.path.join(geckolib, "common", "src", "main", "java")
    sources = []
    for pattern in cfg["sources"]:
        found = sorted(glob.glob(os.path.join(src_root, pattern)))
        if not found:
            raise FileNotFoundError(f"{version}: nada encontrado para {pattern} em {src_root}")
        for path in found:
            dest = os.path.join(work, "src-gl", os.path.relpath(path, src_root))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(path, dest)
            sources.append(dest)
    for group in cfg["stubs"]:
        sources += glob.glob(os.path.join(HERE, "stubs", group, "**", "*.java"), recursive=True)
    sources.append(os.path.join(HERE, cfg["main"] + ".java"))
    classes = os.path.join(work, "classes")
    os.makedirs(classes, exist_ok=True)
    cp = os.pathsep.join(sorted(glob.glob(os.path.join(lib, "*.jar"))))
    subprocess.run(["javac", *cfg["javac"], "-nowarn", "-cp", cp, "-d", classes, *sources],
                   check=True, capture_output=True, text=True)
    return cp + os.pathsep + classes


def run_loader(version: str, classpath: str, files: list[str]) -> list[dict]:
    cfg = VERSIONS[version]
    out = subprocess.run(["java", *cfg["java"], "-cp", classpath, cfg["main"], *files],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def _physical_face(pos: np.ndarray, frm: list[float], to: list[float]) -> str:
    for axis, (lo_name, hi_name) in enumerate((("west", "east"), ("down", "up"), ("north", "south"))):
        if np.allclose(pos[:, axis], pos[0, axis], atol=1e-4):
            return lo_name if abs(pos[0, axis] - frm[axis]) < abs(pos[0, axis] - to[axis]) else hi_name
    raise ValueError("quad não plano")


def compare(bb: dict, baked: dict) -> list[str]:
    """Diferenças entre o que o GeckoLib carregou e o projeto do Blockbench (lista vazia = igual)."""
    problems: list[str] = []
    if not baked.get("ok"):
        return [f"GeckoLib não carregou: {baked.get('error')}"]
    problems += [f"log do GeckoLib: {m}" for m in baked.get("log", [])]
    if not baked.get("format_version_supported"):
        problems.append(f"versão {baked.get('format_version')} não suportada")
    tw, th = bb["resolution"]["width"], bb["resolution"]["height"]
    if (baked["texture_width"], baked["texture_height"]) != (tw, th):
        problems.append("tamanho da textura diferente")
    groups = {g["uuid"]: g for g in bb["groups"]}
    elements = {e["uuid"]: e for e in bb["elements"]}
    expected: dict[str, dict] = {}

    def walk(nodes: list, parent: str | None) -> None:
        for node in nodes:
            g = groups[node["uuid"]]
            expected[g["name"]] = {"group": g, "parent": parent,
                                   "cubes": [elements[c] for c in node["children"] if isinstance(c, str)]}
            walk([c for c in node["children"] if isinstance(c, dict)], g["name"])

    walk(bb["outliner"], None)
    got = {b["name"]: b for b in baked["bones"]}
    if set(got) != set(expected):
        problems.append(f"ossos diferentes: {sorted(set(got) ^ set(expected))}")
    checked_corners = 0
    for name, exp in expected.items():
        b = got.get(name)
        if b is None:
            continue
        g = exp["group"]
        if b.get("parent") != exp["parent"]:  # o Gson omite "parent": null
            problems.append(f"{name}: pai {b.get('parent')} (esperado {exp['parent']})")
        if not np.allclose(b["pivot"], g["origin"], atol=1e-4):
            problems.append(f"{name}: pivô {b['pivot']} (esperado {g['origin']})")
        if not np.allclose(b["rotation_rad"], np.radians(g["rotation"]), atol=1e-5):
            problems.append(f"{name}: rotação {np.degrees(b['rotation_rad']).round(3).tolist()} (esperado {g['rotation']})")
        if len(b["cubes"]) != len(exp["cubes"]):
            problems.append(f"{name}: {len(b['cubes'])} cubos (esperado {len(exp['cubes'])})")
            continue
        for cube, el in zip(b["cubes"], exp["cubes"]):
            label = f"{name}/{el['name']}"
            frm, to = el["from"], el["to"]
            if not np.allclose(cube["size"], np.subtract(to, frm), atol=1e-6):
                problems.append(f"{label}: tamanho {cube['size']}")
            rot = el.get("rotation", [0, 0, 0])
            if any(rot):
                if not np.allclose(cube["pivot"], el.get("origin", [0, 0, 0]), atol=1e-4):
                    problems.append(f"{label}: pivô do cubo {cube['pivot']}")
                if not np.allclose(cube["rotation_rad"], np.radians(rot), atol=1e-5):
                    problems.append(f"{label}: rotação do cubo {cube['rotation_rad']}")
            rects = box_uv_face_rects(frm, to, el.get("uv_offset", [0, 0]), bool(el.get("mirror_uv")))
            afrm, ato = _adjusted_from_to(el)
            faces_seen = set()
            for quad in cube["quads"]:
                verts = np.array(quad["vertices"], dtype=float)
                pos, uv = verts[:, :3] * 16.0, verts[:, 3:] * [tw, th]
                face = _physical_face(pos, afrm, ato)
                faces_seen.add(face)
                expect = np.stack([uv_to_local(face, rects[face], afrm, ato, u, v) for u, v in uv])
                if not np.allclose(pos, expect, atol=2e-3):
                    problems.append(f"{label}: face {face} (GeckoLib {quad['direction']}): UV caem em outro lugar")
                checked_corners += 4
            if faces_seen != {"north", "east", "south", "west", "up", "down"}:
                problems.append(f"{label}: faces {sorted(faces_seen)}")
    baked["_cantos_conferidos"] = checked_corners
    return problems


def tampered_examples(bb: dict) -> list[tuple[str, dict]]:
    """Controle negativo: defeitos plantados de propósito que a comparação PRECISA acusar."""
    import copy

    from ninho_studio.geo import bbmodel_to_geo

    geo = bbmodel_to_geo(bb)

    def bone(g: dict, name: str) -> dict:
        return next(b for b in g["minecraft:geometry"][0]["bones"] if b["name"] == name)

    out = []
    g = copy.deepcopy(geo)
    bone(g, "body")["cubes"][0]["uv"][0] += 1
    out.append(("UV deslocado 1 pixel (quadril)", g))
    g = copy.deepcopy(geo)
    bone(g, "torso")["rotation"][0] *= -1
    out.append(("sinal da rotação X trocado (tronco)", g))
    g = copy.deepcopy(geo)
    c = bone(g, "arm_right")["cubes"][0]
    c["origin"][0] = -c["origin"][0] - c["size"][0]
    out.append(("origem X sem espelhar (braço direito)", g))
    g = copy.deepcopy(geo)
    bone(g, "arm_right")["pivot"][0] *= -1
    out.append(("pivô X sem espelhar (braço direito)", g))
    g = copy.deepcopy(geo)
    bone(g, "torso")["cubes"][0]["mirror"] = True
    out.append(("cubo espelhado sem querer (tronco)", g))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True, help="pasta com os .jar (gson, guava, fastutil, jspecify, annotations, joml)")
    ap.add_argument("--geckolib5", help="checkout do GeckoLib 5 (padrão: baixa o commit testado do GitHub)")
    ap.add_argument("--geckolib4", help="checkout do GeckoLib 4 (padrão: baixa o commit testado do GitHub)")
    args = ap.parse_args()
    from ninho_studio.geo import geo_dumps

    report = {}
    with tempfile.TemporaryDirectory() as work:
        cases = list(all_cases())
        files = []
        for key, _label, _bb, geo_text, _png in cases:
            path = os.path.join(work, f"{key}.geo.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(geo_text)
            files.append(path)
        control_bb = cases[0][2]
        controls = tampered_examples(control_bb)
        control_files = []
        for k, (_name, g) in enumerate(controls):
            path = os.path.join(work, f"controle_{k}.geo.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(geo_dumps(g))
            control_files.append(path)

        for version, cfg in VERSIONS.items():
            vwork = os.path.join(work, version)
            os.makedirs(vwork)
            checkout = getattr(args, version) or fetch_geckolib(os.path.join(vwork, "geckolib"), cfg["commit"])
            commit = subprocess.run(["git", "-C", checkout, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            classpath = build(version, checkout, args.lib, vwork)
            results = run_loader(version, classpath, files + control_files)
            control_rows = []
            for (name, _g), baked in zip(controls, results[len(files):]):
                found = compare(control_bb, baked)
                control_rows.append({"defeito_plantado": name, "acusado": bool(found), "diferencas": found[:3]})
                print(version, "controle:", name, "->", "acusado" if found else "NÃO ACUSADO")
            rows = []
            for (key, label, bb, _geo, _png), baked in zip(cases, results[:len(files)]):
                problems = compare(bb, baked)
                rows.append({
                    "caso": label,
                    "carregou": baked.get("ok", False),
                    "format_version": baked.get("format_version"),
                    "versao_suportada": baked.get("format_version_supported"),
                    "ossos": len(baked.get("bones", [])),
                    "cubos": sum(len(b["cubes"]) for b in baked.get("bones", [])),
                    "cantos_de_face_conferidos": baked.get("_cantos_conferidos", 0),
                    "log_do_geckolib": baked.get("log", []),
                    "diferencas": problems,
                })
                print(version, key, rows[-1]["carregou"], rows[-1]["ossos"], rows[-1]["cubos"],
                      rows[-1]["cantos_de_face_conferidos"], len(problems), problems[:3])
            report[version] = {"geckolib": f"{cfg['label']}, commit {commit}", "casos": rows, "controle_negativo": control_rows}

    doc = {
        "o_que_e": "leitores de geometria do GeckoLib compilados do código-fonte original, sem o Minecraft",
        "substitutos": "classes do Minecraft trocadas por versões mínimas (tools/geckolib_check/stubs)",
        "ninho_model_studio": __version__,
        "data": dt.date.today().isoformat(),
        "o_que_foi_conferido": [
            "o GeckoLib lê cada .geo.json sem erro nem aviso no log, e aceita a versão 1.12.0",
            "ossos: mesmos nomes, pais, pivôs e rotações do projeto do Blockbench",
            "cubos: mesmo tamanho, pivô e rotação",
            "cada canto de cada face: a posição e o UV do GeckoLib caem no mesmo ponto que no Blockbench",
            "controle negativo: defeitos plantados de propósito são acusados",
        ],
        "nao_coberto": "renderização no jogo, registro da criatura e animações (exigem o Minecraft com o mod)",
        **report,
    }
    with open(os.path.join(ROOT, "docs", "verificacao-geckolib-leitor.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
