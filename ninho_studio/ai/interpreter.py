"""Modo IA: descrição livre → CreatureSpec validada.

Fluxo: prompt com exemplos → geração → extração do JSON (sem eval/exec) →
validação pelo esquema → até N tentativas de reparo mostrando os erros ao
modelo. Se nada passar, devolve ``ok=False`` com os erros, e quem chamou deve
oferecer o modo procedural — nunca trocar silenciosamente.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from ..palette import color_name_pt
from ..spec import all_leaf_paths, normalize_spec, validate_spec
from .extract import JSONExtractionError, extract_json
from .prompt import build_messages, repair_message


class TextGenerator(Protocol):
    model_id: str

    def generate(self, messages: list[dict[str, str]], max_new_tokens: int = 700, temperature: float = 0.0,
                 seed: int = 0, stop_when_json_complete: bool = True) -> Any: ...

    def describe(self) -> dict[str, Any]: ...


@dataclass
class AIResult:
    ok: bool
    spec: Optional[dict[str, Any]]
    ai_json: Optional[dict[str, Any]]
    provided_fields: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0
    model: dict[str, Any] = field(default_factory=dict)
    decoding: dict[str, Any] = field(default_factory=dict)

    def info_for_config(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "decoding": self.decoding,
            "attempts": self.attempts,
            "validated_ai_json": self.ai_json,
            "fields_from_ai": self.provided_fields,
            "fields_from_defaults": sorted(set(all_leaf_paths()) - set(self.provided_fields)),
            "warnings": self.warnings,
            "elapsed_s": round(self.seconds, 2),
        }


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")


UNSUPPORTED = {
    "quadrúpede": ["triceratops", "estegossauro", "stegosaurus", "anquilossauro", "ankylosaurus", "braquiossauro",
                   "brachiosaurus", "diplodoco", "lobo", "cachorro", "cao", "gato", "cavalo", "vaca", "urso", "leao",
                   "tigre", "porco", "dragao"],
    "humanoide": ["humano", "homem", "mulher", "zumbi", "esqueleto", "guerreiro", "robo", "cavaleiro", "goblin"],
    "voador": ["pterodactilo", "pteranodonte", "passaro", "aguia", "morcego", "asas"],
}

COLOR_WORDS = ["verde", "vermelho", "azul", "amarelo", "laranja", "marrom", "cinza", "preto", "branco", "roxo", "rosa",
               "dourado", "bege", "creme"]


def _without_name(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if k != "name"}


def semantic_warnings(description: str, spec: dict[str, Any], provided: list[str],
                      ai_json: Optional[dict[str, Any]] = None) -> list[str]:
    """Avisos informativos (não bloqueiam): cópia do exemplo, cobertura, pedidos não suportados e cores citadas."""
    from .prompt import EXAMPLES

    warnings = []
    if ai_json is not None:
        for text, answer in EXAMPLES:
            if _without_name(ai_json) == _without_name(answer) and _norm(text) != _norm(description):
                warnings.append("A IA repetiu um exemplo do prompt em vez de interpretar a descrição; "
                                "reformule a descrição ou aumente a criatividade.")
    text = _norm(description)
    total = len(all_leaf_paths())
    if len(provided) < 0.25 * total:
        warnings.append(f"A IA preencheu só {len(provided)} de {total} campos; os demais vieram do padrão.")
    for plan, words in UNSUPPORTED.items():
        hits = [w for w in words if w in text.split() or f" {w}" in f" {text}"]
        if hits:
            warnings.append(
                f"A descrição cita '{hits[0]}' ({plan}). Esta versão só constrói terópodes (base T-rex); "
                "o resultado usa a base T-rex."
            )
    cited = [w for w in COLOR_WORDS if w in text]
    if cited:
        c = spec["colors"]
        warnings.append(
            "Cores citadas: " + ", ".join(cited) + ". Geradas: principal " + f"{c['primary']} ({color_name_pt(c['primary'])}), "
            f"ventre {c['belly']} ({color_name_pt(c['belly'])}), padrão {c['pattern']} ({color_name_pt(c['pattern'])})."
        )
    return warnings


def interpret(description: str, llm: TextGenerator, *, seed: int = 0, temperature: float = 0.0, max_attempts: int = 3,
              max_new_tokens: int = 700, progress=None) -> AIResult:
    if not description or not description.strip():
        return AIResult(ok=False, spec=None, ai_json=None, errors=["descrição vazia"])
    messages = build_messages(description)
    attempts: list[dict[str, Any]] = []
    t_start = time.perf_counter()
    decoding = {"temperature": temperature, "do_sample": bool(temperature and temperature > 0), "seed": seed,
                "max_new_tokens": max_new_tokens, "max_attempts": max_attempts}
    last_errors: list[str] = []
    for k in range(max_attempts):
        if progress:
            progress(f"IA: tentativa {k + 1} de {max_attempts}…")
        try:
            out = llm.generate(messages, max_new_tokens=max_new_tokens, temperature=temperature, seed=seed + k)
        except Exception as exc:  # noqa: BLE001
            last_errors = [f"erro durante a geração: {type(exc).__name__}: {exc}"]
            attempts.append({"raw_output": None, "errors": last_errors})
            break
        raw = out.text
        record: dict[str, Any] = {"raw_output": raw, "new_tokens": getattr(out, "new_tokens", None),
                                  "seconds": round(getattr(out, "seconds", 0.0), 2)}
        try:
            obj = extract_json(raw)
        except JSONExtractionError as exc:
            last_errors = [str(exc)]
        else:
            last_errors = [str(e) for e in validate_spec(obj)]
            if not last_errors:
                spec, provided = normalize_spec(obj)
                record["errors"] = []
                attempts.append(record)
                result = AIResult(ok=True, spec=spec, ai_json=obj, provided_fields=provided, attempts=attempts,
                                  seconds=time.perf_counter() - t_start, model=llm.describe(), decoding=decoding)
                result.warnings = semantic_warnings(description, spec, provided, obj)
                return result
        record["errors"] = last_errors
        attempts.append(record)
        messages = messages + [{"role": "assistant", "content": raw}, {"role": "user", "content": repair_message(last_errors)}]
    return AIResult(ok=False, spec=None, ai_json=None, attempts=attempts, errors=last_errors,
                    seconds=time.perf_counter() - t_start, model=llm.describe(), decoding=decoding)
