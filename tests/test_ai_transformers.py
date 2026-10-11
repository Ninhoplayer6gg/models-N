"""Testa o caminho real do transformers com um Qwen2 minúsculo de pesos aleatórios.

Não avalia a qualidade da IA (o modelo é aleatório); confere que carregar,
aplicar o chat template, gerar, parar e decodificar funcionam, e que uma
resposta inválida termina em erro claro (sem trocar de modo em silêncio).
"""

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
pytest.importorskip("tokenizers")


@pytest.fixture(scope="module")
def tiny_path(tmp_path_factory):
    from tiny_qwen import make_tiny_qwen

    return make_tiny_qwen(str(tmp_path_factory.mktemp("tinyqwen")))


def test_load_and_generate(tiny_path):
    from ninho_studio.ai import load_llm

    llm = load_llm(tiny_path, device="cpu", progress=lambda m: None)
    d = llm.describe()
    assert d["device"] == "cpu" and d["dtype"] == "float32"
    out = llm.generate([{"role": "user", "content": "oi"}], max_new_tokens=8)
    assert isinstance(out.text, str) and out.new_tokens <= 8
    out2 = llm.generate([{"role": "user", "content": "oi"}], max_new_tokens=8, temperature=0.8, seed=1)
    assert isinstance(out2.text, str)


def test_interpret_with_random_model_fails_cleanly(tiny_path):
    from ninho_studio.ai import interpret, load_llm

    llm = load_llm(tiny_path, device="cpu", progress=lambda m: None)
    res = interpret("Um T-rex verde", llm, max_attempts=2, max_new_tokens=12)
    assert not res.ok
    assert len(res.attempts) == 2 and res.errors


def test_missing_model_raises_llmerror(tmp_path):
    from ninho_studio.ai import LLMError, load_llm

    with pytest.raises(LLMError):
        load_llm(str(tmp_path / "nao_existe"), device="cpu", progress=lambda m: None)
