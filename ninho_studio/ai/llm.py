"""Modelo de linguagem local (pesos abertos) executado com ``transformers``.

Roda dentro do próprio Colab: sem chave de API e sem a IA integrada do
Google. Usa GPU quando existir e CPU como alternativa.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Modelos avaliados para este protótipo. Licenças conferidas nas páginas
# oficiais do Hugging Face (Qwen/...); ver docs/IA-MODELO.md.
MODEL_CHOICES: dict[str, dict[str, Any]] = {
    "Qwen/Qwen2.5-Coder-1.5B-Instruct": {
        "label": "Qwen2.5-Coder 1.5B Instruct (recomendado)",
        "license": "apache-2.0",
        "params": "1,5 bilhão",
        "download_gb": 3.1,
        "notes": "Bom em JSON. Na GPU T4 do Colab leva segundos; na CPU, de 1 a 3 minutos.",
    },
    "Qwen/Qwen2.5-Coder-0.5B-Instruct": {
        "label": "Qwen2.5-Coder 0.5B Instruct (leve, para CPU)",
        "license": "apache-2.0",
        "params": "0,5 bilhão",
        "download_gb": 1.0,
        "notes": "Mais rápido na CPU, porém erra mais e pode precisar de mais tentativas.",
    },
    "Qwen/Qwen2.5-1.5B-Instruct": {
        "label": "Qwen2.5 1.5B Instruct (uso geral)",
        "license": "apache-2.0",
        "params": "1,5 bilhão",
        "download_gb": 3.1,
        "notes": "Alternativa de uso geral, mesmo tamanho do recomendado.",
    },
}
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"


class LLMError(RuntimeError):
    pass


def _version_tuple(text: str) -> tuple[int, ...]:
    out = []
    for part in text.split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    return tuple(out)


@dataclass
class GenerationOutput:
    text: str
    new_tokens: int
    seconds: float


@dataclass
class LocalLLM:
    model_id: str
    model: Any
    tokenizer: Any
    device: str
    dtype: str
    load_seconds: float
    versions: dict[str, str] = field(default_factory=dict)
    revision: Optional[str] = None

    def describe(self) -> dict[str, Any]:
        info = MODEL_CHOICES.get(self.model_id, {})
        return {
            "model_id": self.model_id,
            "revision": self.revision or getattr(getattr(self.model, "config", None), "_commit_hash", None),
            "license": info.get("license", "verifique na página do modelo"),
            "device": self.device,
            "dtype": self.dtype,
            "load_seconds": round(self.load_seconds, 1),
            **self.versions,
        }

    def generate(self, messages: list[dict[str, str]], max_new_tokens: int = 700, temperature: float = 0.0,
                 seed: int = 0, stop_when_json_complete: bool = True) -> GenerationOutput:
        import torch
        from transformers import GenerationConfig, StoppingCriteria, StoppingCriteriaList

        from .extract import json_complete

        tok = self.tokenizer
        try:
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok([prompt], return_tensors="pt").to(self.device)
        prompt_len = int(inputs["input_ids"].shape[1])

        class _JsonDone(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):  # noqa: D401
                text = tok.decode(input_ids[0, prompt_len:], skip_special_tokens=True)
                done = json_complete(text)
                return torch.full((input_ids.shape[0],), done, dtype=torch.bool, device=input_ids.device)

        eos = tok.eos_token_id
        pad = tok.pad_token_id if tok.pad_token_id is not None else eos
        cfg = {"max_new_tokens": int(max_new_tokens), "eos_token_id": eos, "pad_token_id": pad,
               "repetition_penalty": 1.05}
        if temperature and temperature > 0:
            cfg.update(do_sample=True, temperature=float(temperature), top_p=0.9, top_k=40)
        else:
            cfg.update(do_sample=False)
        gen_config = GenerationConfig(**cfg)
        stopping = StoppingCriteriaList([_JsonDone()]) if stop_when_json_complete else None
        torch.manual_seed(int(seed))
        t0 = time.perf_counter()
        with torch.inference_mode():
            out = self.model.generate(**inputs, generation_config=gen_config, stopping_criteria=stopping)
        seconds = time.perf_counter() - t0
        new = out[0, prompt_len:]
        text = tok.decode(new, skip_special_tokens=True)
        return GenerationOutput(text=text, new_tokens=int(new.shape[0]), seconds=seconds)


def load_llm(model_id: str = DEFAULT_MODEL, device: str = "auto", revision: Optional[str] = None,
             progress=print) -> LocalLLM:
    """Baixa (na primeira vez) e carrega o modelo. Lança :class:`LLMError` com mensagem em português."""
    try:
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise LLMError(
            f"bibliotecas da IA ausentes ({exc}). No Google Colab elas já vêm instaladas; "
            "fora dele, instale os pacotes 'torch' e 'transformers'"
        ) from exc

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise LLMError("GPU pedida, mas nenhuma GPU disponível. Use device='cpu' ou ative a GPU no Colab.")
    dtype = torch.float16 if device == "cuda" else torch.float32
    dtype_name = "float16" if device == "cuda" else "float32"
    tv = _version_tuple(transformers.__version__)
    dtype_kw = "dtype" if tv >= (4, 56) else "torch_dtype"
    progress(f"Carregando {model_id} em {device.upper()} ({dtype_name}) — transformers {transformers.__version__}")
    t0 = time.perf_counter()
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision, **{dtype_kw: dtype})
        model.to(device)
        model.eval()
    except torch.cuda.OutOfMemoryError as exc:  # pragma: no cover
        raise LLMError("memória da GPU insuficiente; escolha o modelo 0.5B ou reinicie o ambiente") from exc
    except OSError as exc:
        raise LLMError(f"não foi possível baixar/abrir o modelo '{model_id}': {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"falha ao carregar o modelo '{model_id}': {type(exc).__name__}: {exc}") from exc
    seconds = time.perf_counter() - t0
    versions = {"transformers_version": transformers.__version__, "torch_version": torch.__version__}
    return LocalLLM(model_id=model_id, model=model, tokenizer=tokenizer, device=device, dtype=dtype_name,
                    load_seconds=seconds, versions=versions, revision=revision)
