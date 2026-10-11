"""Fluxo completo: parâmetros → modelo → atlas UV → textura → .bbmodel → validação.

O fluxo não depende da IA. No modo IA a spec vem do intérprete
(:mod:`ninho_studio.ai`), já validada; no modo procedural ela vem dos
controles manuais. Os dois caminhos terminam aqui.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from . import __version__
from .atlas import AtlasError, AtlasInfo, assign_uvs
from .bbmodel import (
    BLOCKBENCH_REFERENCE_VERSION,
    FORMAT_VERSION,
    MODEL_FORMAT,
    model_to_bbmodel,
    png_bytes,
    sanitize_identifier,
)
from .builders import build_model
from .model import Model
from .spec import SPEC_VERSION, BuildSettings, SpecValidationError, normalize_spec, validate_spec
from .texture import paint_texture
from .validate import ValidationReport, validate_bbmodel

MODES = ("ia", "procedural")


@dataclass
class GenerationResult:
    spec: dict[str, Any]
    settings: BuildSettings
    model: Model
    bbmodel: dict[str, Any]
    texture: np.ndarray
    png: bytes
    validation: ValidationReport
    atlas: AtlasInfo
    notes: list[str]
    config: dict[str, Any]
    base_name: str
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.validation.ok


def generate(
    spec: dict[str, Any],
    settings: BuildSettings,
    *,
    mode: str,
    description: str = "",
    ai_info: Optional[dict[str, Any]] = None,
    manual_adjustments: Optional[dict[str, Any]] = None,
    extra_notes: Optional[list[str]] = None,
    base_name: Optional[str] = None,
) -> GenerationResult:
    """Gera o modelo a partir de uma spec completa e validada."""
    if mode not in MODES:
        raise ValueError(f"modo inválido: {mode!r} (use 'ia' ou 'procedural')")
    if mode == "ia" and not ai_info:
        raise ValueError("modo 'ia' exige as informações da execução da IA (ai_info)")
    problems = settings.validate()
    if problems:
        raise ValueError("; ".join(problems))
    errors = validate_spec(spec)
    if errors:
        raise SpecValidationError(errors)
    spec, _provided = normalize_spec(spec)

    t0 = time.perf_counter()
    model, notes, atlas, spec = _build_and_pack(spec, settings)
    notes += color_notes(spec)
    model.meta["seed"] = settings.seed
    t1 = time.perf_counter()
    if atlas.upgraded:
        notes.append(
            f"textura: o atlas não coube em {settings.texture_size}x{settings.texture_size}; usada {atlas.size}x{atlas.size}"
        )
    model.assign_uuids(settings.seed)
    texture = paint_texture(model, spec, settings.seed)
    t2 = time.perf_counter()
    png = png_bytes(texture)
    name = base_name or sanitize_identifier(spec.get("name") or "trex")
    bb = model_to_bbmodel(model, png, f"{name}.png", identifier=name)
    report = validate_bbmodel(bb, element_budget=settings.element_budget, texture=texture)
    t3 = time.perf_counter()
    notes = list(extra_notes or []) + notes

    config = build_config(
        spec=spec,
        settings=settings,
        mode=mode,
        description=description,
        ai_info=ai_info,
        manual_adjustments=manual_adjustments,
        model=model,
        bbmodel=bb,
        png=png,
        atlas=atlas,
        report=report,
        notes=notes,
        name=name,
    )
    return GenerationResult(
        spec=spec,
        settings=settings,
        model=model,
        bbmodel=bb,
        texture=texture,
        png=png,
        validation=report,
        atlas=atlas,
        notes=notes,
        config=config,
        base_name=name,
        timings={"construcao_s": t1 - t0, "uv_textura_s": t2 - t1, "exportacao_validacao_s": t3 - t2},
    )


def color_notes(spec: dict[str, Any]) -> list[str]:
    """Avisos quando a barriga quase não se distingue do corpo (contraste baixo)."""
    from .palette import contrast_ratio, hex_to_rgb, luminance, rgb_to_hex, shade

    colors = spec["colors"]
    prim, belly = hex_to_rgb(colors["primary"]), hex_to_rgb(colors["belly"])
    ratio = contrast_ratio(prim, belly)
    if ratio >= 1.15:
        return []
    suggestion = "#e6d6a8" if luminance(prim) > 0.6 else rgb_to_hex(shade(prim, 3))
    return [
        f"barriga {colors['belly']} quase igual à cor principal {colors['primary']} (contraste {ratio:.2f}); "
        f"para destacar o ventre, use cor_barriga na Etapa 3 (ex.: {suggestion})"
    ]


def _build_and_pack(spec: dict[str, Any], settings: BuildSettings):
    """Monta o modelo e o atlas; se não couber nem em 256x256, reduz a escala aos poucos (com aviso)."""
    requested_scale = float(spec["scale"])
    current = dict(spec)
    while True:
        model, notes = build_model(current, settings)
        try:
            atlas = assign_uvs(model, settings.texture_size, settings.auto_texture_upgrade)
        except AtlasError:
            next_scale = round(float(current["scale"]) - 0.1, 2)
            if next_scale < 0.6 - 1e-9:
                raise
            current = {**current, "scale": next_scale}
            continue
        if float(current["scale"]) != requested_scale:
            notes.append(
                f"escala reduzida de {requested_scale:g} para {float(current['scale']):g} para o atlas caber na "
                f"textura {atlas.size}x{atlas.size}"
            )
        return model, notes, atlas, current


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_config(*, spec, settings, mode, description, ai_info, manual_adjustments, model, bbmodel, png, atlas, report,
                 notes, name) -> dict[str, Any]:
    from .bbmodel import dumps

    return {
        "tool": "Ninho Model Studio",
        "version": __version__,
        "spec_version": SPEC_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "mode": mode,
        "mode_label": "IA (descrição livre interpretada pelo modelo de linguagem)" if mode == "ia"
        else "Procedural (parâmetros preenchidos manualmente)",
        "description": description,
        "seed": settings.seed,
        "parameters": spec,
        "manual_adjustments": manual_adjustments or None,
        "ai": ai_info,
        "settings": {
            "texture_size_requested": settings.texture_size,
            "texture_size": atlas.size,
            "element_budget": settings.element_budget,
            "auto_texture_upgrade": settings.auto_texture_upgrade,
        },
        "texture_generation": "procedural (regras determinísticas a partir da seed; não usa IA)",
        "result": {
            "cubes": model.cube_count,
            "bones": len(model.bones),
            "structure": model.meta.get("structure"),
            "extras": model.meta.get("extras"),
            "atlas_usage": round(atlas.usage, 3),
            "atlas_strategy": atlas.strategy,
        },
        "validation": report.to_dict(),
        "files": {
            "bbmodel": f"{name}.bbmodel",
            "texture": f"{name}.png",
            "sha256": {
                f"{name}.bbmodel": _sha256(dumps(bbmodel).encode("utf-8")),
                f"{name}.png": _sha256(png),
            },
        },
        "blockbench": {
            "format_version": FORMAT_VERSION,
            "model_format": MODEL_FORMAT,
            "box_uv": True,
            "reference_version": BLOCKBENCH_REFERENCE_VERSION,
            "note": "Projeto editável do Blockbench. Para o Minecraft, exporte no Blockbench (ex.: Bedrock Geometry).",
        },
        "notes": notes,
        "reproduce": "Use 'parameters', 'seed' e 'settings' no modo procedural para obter o mesmo .bbmodel e o mesmo .png.",
    }


def regenerate_from_config(config: dict[str, Any]) -> GenerationResult:
    """Refaz o modelo a partir de um .json gerado antes (não precisa da IA)."""
    s = config["settings"]
    settings = BuildSettings(
        seed=int(config["seed"]),
        texture_size=int(s.get("texture_size_requested", s.get("texture_size", 128))),
        element_budget=int(s["element_budget"]),
        auto_texture_upgrade=bool(s.get("auto_texture_upgrade", True)),
    )
    name = config.get("files", {}).get("bbmodel", "trex.bbmodel").rsplit(".", 1)[0]
    return generate(config["parameters"], settings, mode="procedural", description=config.get("description", ""),
                    base_name=name)
