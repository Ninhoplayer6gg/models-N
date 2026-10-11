"""Modo IA: modelo de linguagem local que transforma a descrição em dados estruturados."""

from .extract import JSONExtractionError, extract_json
from .interpreter import AIResult, interpret
from .llm import DEFAULT_MODEL, MODEL_CHOICES, LLMError, LocalLLM, load_llm

__all__ = [
    "AIResult",
    "DEFAULT_MODEL",
    "JSONExtractionError",
    "LLMError",
    "LocalLLM",
    "MODEL_CHOICES",
    "extract_json",
    "interpret",
    "load_llm",
]
