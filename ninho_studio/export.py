"""Gravação dos arquivos de saída e do pacote .zip."""

from __future__ import annotations

import json
import os
import zipfile
from typing import Any

from .bbmodel import dumps
from .mesh import build_mesh
from .pipeline import GenerationResult
from .render import atlas_debug, contact_sheet, skeleton_sheet
from .viewer import viewer_html

README_TXT = """Ninho Model Studio — {name}
=================================

Arquivos deste pacote
---------------------
{name}.bbmodel   Projeto EDITÁVEL do Blockbench (formato {fmt}, versão do arquivo {ver}),
                 com cubos, grupos (ossos), pivôs, UV e a textura embutida.
{name}.png       Textura ({tex}x{tex}) gerada de forma PROCEDURAL (regras + seed, sem IA).
{name}.json      Configuração: modo ({mode}), descrição, parâmetros, seed, versão e validação.
{name}_vistas.png      Vistas: perspectiva, lado, frente, topo, traseira e ventre.
{name}_atlas.png       Atlas UV ampliado com o nome de cada cubo e a letra de cada face
                       (N=norte/frente, S=sul/trás, L=leste/direita do animal, O=oeste/esquerda,
                       C=cima, B=baixo).
{name}_esqueleto.png   Pivôs (pontos vermelhos) e hierarquia dos ossos (linhas azuis).
{name}_3d.html         Visualizador 3D (abra no navegador; funciona offline).

Projeto editável x formatos do Minecraft
----------------------------------------
O .bbmodel é o arquivo de trabalho do Blockbench; o jogo não lê .bbmodel.
Para usar no Minecraft, abra o .bbmodel no Blockbench (app ou https://web.blockbench.net)
e exporte para o formato do destino:
  * Bedrock: File > Export > Export Bedrock Geometry (.geo.json) + a textura .png.
  * GeckoLib / Java: exportadores específicos ficam para uma etapa posterior.

A criatura olha para -Z (norte), com o lado direito em +X, pés em Y=0.
"""


def save_outputs(result: GenerationResult, out_dir: str, previews: bool = True, viewer: bool = True) -> dict[str, Any]:
    """Grava os arquivos e o .zip. Retorna os caminhos gerados."""
    os.makedirs(out_dir, exist_ok=True)
    name = result.base_name
    paths: dict[str, Any] = {}

    def write_bytes(fname: str, data: bytes) -> str:
        path = os.path.join(out_dir, fname)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    paths["bbmodel"] = write_bytes(f"{name}.bbmodel", dumps(result.bbmodel).encode("utf-8"))
    paths["png"] = write_bytes(f"{name}.png", result.png)
    paths["json"] = write_bytes(f"{name}.json", (json.dumps(result.config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    mesh = build_mesh(result.bbmodel)
    if previews:
        title = f"{result.spec.get('name', name)} — {result.model.cube_count} cubos, textura {result.atlas.size}x{result.atlas.size}"
        sheet = contact_sheet(mesh, result.texture, title=title)
        paths["vistas"] = os.path.join(out_dir, f"{name}_vistas.png")
        sheet.convert("RGB").save(paths["vistas"])
        paths["atlas"] = os.path.join(out_dir, f"{name}_atlas.png")
        atlas_debug(result.bbmodel, result.texture).save(paths["atlas"])
        paths["esqueleto"] = os.path.join(out_dir, f"{name}_esqueleto.png")
        skeleton_sheet(mesh, result.texture).convert("RGB").save(paths["esqueleto"])
    if viewer:
        html = viewer_html(mesh, result.png, title=f"{result.spec.get('name', name)} — Ninho Model Studio")
        paths["html"] = write_bytes(f"{name}_3d.html", html.encode("utf-8"))

    readme = README_TXT.format(
        name=name,
        fmt=result.config["blockbench"]["model_format"],
        ver=result.config["blockbench"]["format_version"],
        tex=result.atlas.size,
        mode=result.config["mode"],
    )
    paths["leia_me"] = write_bytes("LEIA-ME.txt", readme.encode("utf-8"))

    zip_path = os.path.join(out_dir, f"{name}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for key in ("bbmodel", "png", "json", "vistas", "atlas", "esqueleto", "html", "leia_me"):
            if key in paths:
                zf.write(paths[key], arcname=os.path.basename(paths[key]))
    paths["zip"] = zip_path
    return paths
