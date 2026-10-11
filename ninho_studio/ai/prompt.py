"""Instruções e exemplos enviados ao modelo de linguagem."""

from __future__ import annotations

import json

from ..spec import COLORS, DETAIL_LEVELS, FEATURES, PATTERN_TYPES, PROPORTIONS, SCALE_RANGE, SKIN_TYPES


def _schema_lines() -> str:
    props = ", ".join(f'"{k}": {lo}-{hi}' for k, (lo, hi, _d, _desc) in PROPORTIONS.items())
    colors = ", ".join(f'"{k}"' for k in COLORS)
    feats = ", ".join(f'"{k}"' for k in FEATURES)
    return (
        "{\n"
        '  "species": "t_rex",\n'
        '  "name": short creature name (max 40 characters),\n'
        f'  "scale": {SCALE_RANGE[0]}-{SCALE_RANGE[1]} (overall size, 1 = normal),\n'
        f'  "proportions": {{{props}}},\n'
        f'  "colors": {{{colors}}} (each "#rrggbb"),\n'
        f'  "pattern": {{"type": one of {list(PATTERN_TYPES)}, "intensity": 0.0-1.0}},\n'
        f'  "skin": one of {list(SKIN_TYPES)},\n'
        f'  "features": {{{feats}}} (true/false),\n'
        f'  "detail_level": one of {list(DETAIL_LEVELS)}\n'
        "}"
    )


SYSTEM_PROMPT = (
    "You convert a creature description (usually in Brazilian Portuguese) into ONE JSON object for a "
    "Minecraft-style T-rex model builder.\n"
    "Rules:\n"
    "- Answer with the JSON object only. No explanations, no markdown, no comments.\n"
    "- Use only the keys below. Numbers must stay inside the ranges. Colors must be hex strings like \"#4f7a35\".\n"
    "- 1.0 means a normal T-rex. Change a value only when the description asks for it.\n"
    "Schema:\n" + _schema_lines() + "\n"
    "Meaning of the proportions: head_size = head size; snout_length = snout length; jaw_open = mouth opening "
    "(0 closed, 1 roaring); neck_length; body_length; body_bulk = muscular/fat (>1) or slim (<1); arm_length; "
    "leg_length; leg_thickness; tail_length; tail_thickness.\n"
    "Colors: primary = main skin (back and sides); secondary = lighter tone of the sides; belly = underside, "
    "usually lighter; pattern = stripes/spots color; eyes; claws = claws and teeth; mouth = inside of the mouth.\n"
    "Portuguese hints: cabeça grande/enorme -> head_size 1.3-1.5; cabeça pequena -> 0.75; focinho longo -> "
    "snout_length 1.3; boca aberta/rugindo -> jaw_open 0.8-1.0; boca fechada -> 0.0; musculoso/robusto/gordo -> "
    "body_bulk 1.25; magro/esguio -> 0.8; braços minúsculos -> arm_length 0.6; braços grandes -> 1.5; "
    "pernas longas -> leg_length 1.25; pernas grossas -> leg_thickness 1.3; cauda longa -> tail_length 1.35; "
    "cauda curta -> 0.7; gigante -> scale 1.4; filhote/pequeno -> scale 0.7 with head_size 1.2; "
    "listras -> stripes; manchas/pintas -> spots; faixas/anéis -> bands; camuflado/mosqueado -> mottled; "
    "sem padrão/liso -> none; escamas -> scales; pele rugosa/blindada -> rough; pele lisa -> smooth; "
    "penas/emplumado -> feathered; chifres -> brow_horns; espinhos -> back_spikes; cicatrizes -> scars; "
    "crista de penas -> feather_crest; pouco detalhado/simples -> low; muito detalhado -> high."
)

# Exemplos propositalmente diferentes da descrição padrão do notebook: no primeiro teste real
# (Colab, T4) o modelo copiou as proporções de um exemplo parecido demais com o pedido.
EXAMPLES = [
    (
        "T-rex marrom-escuro, musculoso e enorme, cabeça grande, manchas pretas, olhos vermelhos, rugindo.",
        {
            "species": "t_rex",
            "name": "T-rex marrom",
            "scale": 1.35,
            "proportions": {
                "head_size": 1.3, "snout_length": 1.0, "jaw_open": 1.0, "neck_length": 1.0, "body_length": 1.05,
                "body_bulk": 1.3, "arm_length": 1.0, "leg_length": 1.0, "leg_thickness": 1.25, "tail_length": 1.0,
                "tail_thickness": 1.15,
            },
            "colors": {
                "primary": "#5a3d26", "secondary": "#7a5636", "belly": "#d9c39a", "pattern": "#1e1410",
                "eyes": "#d42020", "claws": "#e8dcc4", "mouth": "#7a2222",
            },
            "pattern": {"type": "spots", "intensity": 0.7},
            "skin": "rough",
            "features": {"brow_horns": False, "back_spikes": False, "teeth_visible": True, "scars": False,
                         "feather_crest": False},
            "detail_level": "medium",
        },
    ),
    (
        "Filhote de tiranossauro verde-claro com listras finas, pernas longas, cauda curta e boca fechada. Bem simples.",
        {
            "species": "t_rex",
            "name": "Filhote verde",
            "scale": 0.7,
            "proportions": {
                "head_size": 1.2, "snout_length": 0.85, "jaw_open": 0.0, "neck_length": 1.0, "body_length": 0.95,
                "body_bulk": 0.9, "arm_length": 1.0, "leg_length": 1.25, "leg_thickness": 0.9, "tail_length": 0.7,
                "tail_thickness": 0.9,
            },
            "colors": {
                "primary": "#7fb04a", "secondary": "#9cc766", "belly": "#eef0c8", "pattern": "#3f6a25",
                "eyes": "#e0a02a", "claws": "#efe6d2", "mouth": "#9a4040",
            },
            "pattern": {"type": "stripes", "intensity": 0.4},
            "skin": "smooth",
            "features": {"brow_horns": False, "back_spikes": False, "teeth_visible": False, "scars": False,
                         "feather_crest": False},
            "detail_level": "low",
        },
    ),
]


def build_messages(description: str) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for text, answer in EXAMPLES:
        messages.append({"role": "user", "content": f"Descrição: {text}"})
        messages.append({"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)})
    messages.append({"role": "user", "content": f"Descrição: {description.strip()}"})
    return messages


def repair_message(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors[:12])
    return (
        "Your JSON was rejected by the validator:\n"
        f"{lines}\n"
        "Fix these problems and answer again with the complete JSON object only."
    )
