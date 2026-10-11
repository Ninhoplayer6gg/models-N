"""Extração segura do objeto JSON na resposta do modelo.

Nunca usa ``eval``/``exec``: procura o primeiro objeto ``{...}`` com chaves
balanceadas (respeitando textos entre aspas) e o lê com ``json.loads``.
"""

from __future__ import annotations

import json
import re
from typing import Any


class JSONExtractionError(ValueError):
    pass


def strip_reasoning(text: str) -> str:
    """Remove blocos ``<think>...</think>`` (modelos com raciocínio) e cercas de código."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.replace("```json", "```")


def find_json_object(text: str) -> str:
    text = strip_reasoning(text)
    start = text.find("{")
    if start < 0:
        raise JSONExtractionError("a resposta não contém nenhum objeto JSON (falta '{')")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise JSONExtractionError("o objeto JSON da resposta está incompleto (chaves não fecham)")


def extract_json(text: str) -> Any:
    raw = find_json_object(text)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JSONExtractionError(f"JSON inválido: {exc.msg} (linha {exc.lineno}, coluna {exc.colno})") from exc
    if not isinstance(obj, dict):
        raise JSONExtractionError("o JSON precisa ser um objeto {...}")
    return obj


def json_complete(text: str) -> bool:
    """True quando ``text`` já contém um objeto JSON fechado (usado para parar a geração cedo)."""
    try:
        find_json_object(text)
        return True
    except JSONExtractionError:
        return False
