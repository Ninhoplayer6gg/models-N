"""Esquema da criatura (CreatureSpec): definição, validação e ajustes.

O mesmo esquema é usado nos dois modos:

* **Modo IA** – o modelo de linguagem devolve um objeto JSON que precisa
  passar por :func:`validate_spec` antes de ser usado.
* **Modo procedural** – os controles do notebook montam o mesmo objeto, que
  também é validado.

O esquema é um JSON Schema (draft 2020-12) gerado por :func:`json_schema`.
:func:`validate_spec` interpreta esse mesmo dicionário (subconjunto de
palavras-chave: ``type``, ``enum``, ``minimum``, ``maximum``, ``minLength``,
``maxLength``, ``pattern``, ``required``, ``properties`` e
``additionalProperties``), de modo que existe uma única fonte de verdade.
Os testes conferem que o resultado bate com a biblioteca oficial
``jsonschema``.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Any

SPEC_VERSION = "1.0"

# Espécies/presets disponíveis. A chave aponta para o construtor ("body plan").
SPECIES = {
    "t_rex": "theropod",
}

# chave: (mínimo, máximo, padrão, descrição em português)
PROPORTIONS: dict[str, tuple[float, float, float, str]] = {
    "head_size": (0.6, 1.6, 1.0, "tamanho da cabeça"),
    "snout_length": (0.6, 1.6, 1.0, "comprimento do focinho"),
    "jaw_open": (0.0, 1.0, 0.35, "abertura da boca (0 = fechada, 1 = rugindo)"),
    "neck_length": (0.6, 1.6, 1.0, "comprimento do pescoço"),
    "body_length": (0.7, 1.4, 1.0, "comprimento do tronco"),
    "body_bulk": (0.7, 1.4, 1.0, "volume/robustez do tronco"),
    "arm_length": (0.5, 1.8, 1.0, "tamanho dos braços"),
    "leg_length": (0.7, 1.4, 1.0, "comprimento das pernas"),
    "leg_thickness": (0.7, 1.4, 1.0, "espessura das pernas"),
    "tail_length": (0.6, 1.6, 1.0, "comprimento da cauda"),
    "tail_thickness": (0.7, 1.4, 1.0, "espessura da cauda"),
}

SCALE_RANGE = (0.6, 1.6)

# Cores padrão (T-rex verde) e descrição de cada uma.
COLORS: dict[str, tuple[str, str]] = {
    "primary": ("#4f7a35", "cor principal (dorso e laterais)"),
    "secondary": ("#78a04a", "cor secundária (transição lateral)"),
    "belly": ("#dcd3a2", "barriga/ventre (mais clara)"),
    "pattern": ("#2b4524", "cor do padrão (listras, manchas...)"),
    "eyes": ("#f2c12e", "olhos"),
    "claws": ("#ebe3cb", "garras e dentes"),
    "mouth": ("#8a2c2c", "interior da boca"),
}

PATTERN_TYPES = ("none", "stripes", "spots", "bands", "mottled")
SKIN_TYPES = ("scales", "rough", "smooth", "feathered")
DETAIL_LEVELS = ("low", "medium", "high")

# chave: (padrão, descrição)
FEATURES: dict[str, tuple[bool, str]] = {
    "brow_horns": (False, "chifres pequenos sobre os olhos"),
    "back_spikes": (False, "espinhos nas costas"),
    "teeth_visible": (True, "dentes visíveis"),
    "scars": (False, "cicatrizes"),
    "feather_crest": (False, "crista de penas na nuca"),
}

HEX_PATTERN = r"^#[0-9a-fA-F]{6}$"

# Tradução de rótulos usados na interface (português <-> valores do esquema).
PATTERN_LABELS_PT = {
    "none": "nenhum",
    "stripes": "listras",
    "spots": "manchas",
    "bands": "faixas",
    "mottled": "mosqueado",
}
SKIN_LABELS_PT = {
    "scales": "escamas",
    "rough": "rugosa",
    "smooth": "lisa",
    "feathered": "penas",
}
DETAIL_LABELS_PT = {"low": "baixo", "medium": "médio", "high": "alto"}


def _r(x: float) -> float:
    return float(round(x, 4))


def json_schema() -> dict[str, Any]:
    """Retorna o JSON Schema (draft 2020-12) da CreatureSpec."""
    props_schema = {
        key: {
            "type": "number",
            "minimum": lo,
            "maximum": hi,
            "description": desc,
        }
        for key, (lo, hi, _default, desc) in PROPORTIONS.items()
    }
    colors_schema = {
        key: {"type": "string", "pattern": HEX_PATTERN, "description": desc}
        for key, (_default, desc) in COLORS.items()
    }
    features_schema = {
        key: {"type": "boolean", "description": desc}
        for key, (_default, desc) in FEATURES.items()
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/Ninhoplayer6gg/models-N/schema/creature-spec-1.0.json",
        "title": "Ninho Model Studio - CreatureSpec",
        "description": (
            "Descrição estruturada de uma criatura para o construtor procedural. "
            "Campos ausentes recebem valores padrão."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["species"],
        "properties": {
            "species": {"type": "string", "enum": list(SPECIES)},
            "name": {"type": "string", "minLength": 1, "maxLength": 40},
            "scale": {
                "type": "number",
                "minimum": SCALE_RANGE[0],
                "maximum": SCALE_RANGE[1],
                "description": "tamanho geral (1 = normal)",
            },
            "proportions": {
                "type": "object",
                "additionalProperties": False,
                "properties": props_schema,
            },
            "colors": {
                "type": "object",
                "additionalProperties": False,
                "properties": colors_schema,
            },
            "pattern": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string", "enum": list(PATTERN_TYPES)},
                    "intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
            "skin": {"type": "string", "enum": list(SKIN_TYPES)},
            "features": {
                "type": "object",
                "additionalProperties": False,
                "properties": features_schema,
            },
            "detail_level": {"type": "string", "enum": list(DETAIL_LEVELS)},
        },
    }


def default_spec(species: str = "t_rex") -> dict[str, Any]:
    """Spec completa com os valores padrão (T-rex verde)."""
    if species not in SPECIES:
        raise ValueError(f"espécie desconhecida: {species!r}")
    return {
        "species": species,
        "name": "T-rex",
        "scale": 1.0,
        "proportions": {k: v[2] for k, v in PROPORTIONS.items()},
        "colors": {k: v[0] for k, v in COLORS.items()},
        "pattern": {"type": "stripes", "intensity": 0.55},
        "skin": "scales",
        "features": {k: v[0] for k, v in FEATURES.items()},
        "detail_level": "medium",
    }


# ---------------------------------------------------------------------------
# Validação (interpretador do subconjunto de JSON Schema usado acima)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecError:
    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.path or '(raiz)'}: {self.message}"


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        return math.isfinite(float(value))
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    raise ValueError(f"tipo de esquema não suportado: {expected}")


_TYPE_PT = {
    "object": "objeto",
    "string": "texto",
    "boolean": "verdadeiro/falso (true/false)",
    "integer": "número inteiro",
    "number": "número",
    "array": "lista",
    "null": "null",
}


def _validate_node(value: Any, schema: dict[str, Any], path: str, errors: list[SpecError]) -> None:
    expected = schema.get("type")
    if expected is not None and not _type_ok(value, expected):
        errors.append(SpecError(path, f"deveria ser {_TYPE_PT.get(expected, expected)}, recebido {json_repr(value)}"))
        return
    if "enum" in schema and value not in schema["enum"]:
        opcoes = ", ".join(str(v) for v in schema["enum"])
        errors.append(SpecError(path, f"valor {json_repr(value)} não permitido (use: {opcoes})"))
    if expected == "number" or expected == "integer":
        lo = schema.get("minimum")
        hi = schema.get("maximum")
        if lo is not None and value < lo or hi is not None and value > hi:
            errors.append(SpecError(path, f"valor {value} fora do intervalo [{lo}, {hi}]"))
    if expected == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(SpecError(path, f"texto curto demais (mínimo {schema['minLength']})"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(SpecError(path, f"texto longo demais (máximo {schema['maxLength']} caracteres)"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            if schema["pattern"] == HEX_PATTERN:
                errors.append(SpecError(path, f"{json_repr(value)} não é uma cor hexadecimal no formato #rrggbb"))
            else:
                errors.append(SpecError(path, f"{json_repr(value)} não segue o padrão {schema['pattern']}"))
    if expected == "object":
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append(SpecError(_join(path, req), "campo obrigatório ausente"))
        for key, sub in value.items():
            if key in props:
                _validate_node(sub, props[key], _join(path, key), errors)
            elif schema.get("additionalProperties", True) is False:
                validas = ", ".join(props)
                errors.append(SpecError(_join(path, key), f"chave desconhecida (chaves válidas: {validas})"))


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def json_repr(value: Any) -> str:
    import json

    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def validate_spec(obj: Any) -> list[SpecError]:
    """Valida ``obj`` contra o JSON Schema. Retorna a lista de erros (vazia = válido)."""
    errors: list[SpecError] = []
    _validate_node(obj, json_schema(), "", errors)
    return errors


class SpecValidationError(ValueError):
    def __init__(self, errors: list[SpecError]):
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors))


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _leaf_paths(obj: dict[str, Any], prefix: str = "") -> list[str]:
    paths = []
    for key, value in obj.items():
        path = _join(prefix, key)
        if isinstance(value, dict):
            paths.extend(_leaf_paths(value, path))
        else:
            paths.append(path)
    return paths


def normalize_spec(partial: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Valida e completa uma spec parcial com os valores padrão.

    Retorna ``(spec_completa, campos_fornecidos)``. Lança
    :class:`SpecValidationError` se a spec não seguir o esquema.
    """
    errors = validate_spec(partial)
    if errors:
        raise SpecValidationError(errors)
    full = _deep_merge(default_spec(partial["species"]), partial)
    full["scale"] = float(full["scale"])
    for key in PROPORTIONS:
        full["proportions"][key] = float(full["proportions"][key])
    full["pattern"]["intensity"] = float(full["pattern"]["intensity"])
    for key in COLORS:
        full["colors"][key] = full["colors"][key].lower()
    provided = sorted(_leaf_paths(partial))
    final_errors = validate_spec(full)
    if final_errors:  # pragma: no cover - defesa extra
        raise SpecValidationError(final_errors)
    return full, provided


def all_leaf_paths() -> list[str]:
    return sorted(_leaf_paths(default_spec()))


# ---------------------------------------------------------------------------
# Ajustes manuais (multiplicadores e substituições)
# ---------------------------------------------------------------------------


def apply_adjustments(spec: dict[str, Any], adjustments: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Aplica ajustes manuais a uma spec completa.

    ``adjustments`` aceita:

    * ``proportions``: multiplicadores (1.0 = sem mudança);
    * ``scale``: multiplicador do tamanho geral;
    * ``colors``: cores ``#rrggbb`` que substituem as atuais;
    * ``pattern_type``, ``pattern_intensity``, ``skin``, ``detail_level``,
      ``jaw_open``: substituições diretas (``None`` = manter);
    * ``features``: dicionário de booleanos que substituem os atuais.

    Valores são limitados aos intervalos do esquema; cada limitação gera um
    aviso na lista retornada.
    """
    out = copy.deepcopy(spec)
    notes: list[str] = []
    if not adjustments:
        return out, notes

    def clamp(name: str, value: float, lo: float, hi: float) -> float:
        if value < lo or value > hi:
            limited = min(hi, max(lo, value))
            notes.append(f"{name}: {value:.2f} limitado a {limited:.2f} (intervalo {lo}–{hi})")
            return limited
        return value

    for key, mult in (adjustments.get("proportions") or {}).items():
        if key not in PROPORTIONS:
            raise ValueError(f"proporção desconhecida: {key}")
        if mult is None or float(mult) == 1.0:
            continue
        lo, hi, _d, _desc = PROPORTIONS[key]
        out["proportions"][key] = _r(clamp(f"proportions.{key}", out["proportions"][key] * float(mult), lo, hi))

    if adjustments.get("jaw_open") is not None:
        lo, hi, _d, _desc = PROPORTIONS["jaw_open"]
        out["proportions"]["jaw_open"] = _r(clamp("proportions.jaw_open", float(adjustments["jaw_open"]), lo, hi))

    scale_mult = adjustments.get("scale")
    if scale_mult is not None and float(scale_mult) != 1.0:
        out["scale"] = _r(clamp("scale", out["scale"] * float(scale_mult), *SCALE_RANGE))

    for key, value in (adjustments.get("colors") or {}).items():
        if key not in COLORS:
            raise ValueError(f"cor desconhecida: {key}")
        if not value:
            continue
        value = normalize_hex(value)
        out["colors"][key] = value

    if adjustments.get("pattern_type"):
        out["pattern"]["type"] = adjustments["pattern_type"]
    if adjustments.get("pattern_intensity") is not None:
        out["pattern"]["intensity"] = _r(clamp("pattern.intensity", float(adjustments["pattern_intensity"]), 0.0, 1.0))
    if adjustments.get("skin"):
        out["skin"] = adjustments["skin"]
    if adjustments.get("detail_level"):
        out["detail_level"] = adjustments["detail_level"]
    for key, value in (adjustments.get("features") or {}).items():
        if key not in FEATURES:
            raise ValueError(f"característica desconhecida: {key}")
        if value is not None:
            out["features"][key] = bool(value)
    if adjustments.get("name"):
        out["name"] = str(adjustments["name"])[:40]

    errors = validate_spec(out)
    if errors:
        raise SpecValidationError(errors)
    return out, notes


def normalize_hex(value: str) -> str:
    """Aceita ``#abc``, ``abc``, ``#aabbcc`` ou ``aabbcc`` e devolve ``#aabbcc``."""
    text = str(value).strip().lower()
    if not text.startswith("#"):
        text = "#" + text
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        text = "#" + "".join(ch * 2 for ch in text[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", text):
        raise ValueError(f"cor inválida: {value!r} (use o formato #rrggbb, ex.: #4f7a35)")
    return text


@dataclass
class BuildSettings:
    """Configurações técnicas (não descrevem a criatura)."""

    seed: int = 42
    texture_size: int = 128  # 128 ou 256
    element_budget: int = 96
    auto_texture_upgrade: bool = True

    def validate(self) -> list[str]:
        problems = []
        if self.texture_size not in (128, 256):
            problems.append("texture_size deve ser 128 ou 256")
        if not (16 <= int(self.element_budget) <= 256):
            problems.append("element_budget deve ficar entre 16 e 256")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            problems.append("seed deve ser um número inteiro")
        return problems
