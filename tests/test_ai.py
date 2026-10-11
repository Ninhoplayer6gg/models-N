import ast
import json
import os

import pytest

from ninho_studio.ai import JSONExtractionError, extract_json, interpret
from ninho_studio.ai.extract import json_complete
from ninho_studio.ai.prompt import EXAMPLES, build_messages
from ninho_studio.spec import validate_spec

GOOD = json.dumps({"species": "t_rex", "name": "Rex azul", "colors": {"primary": "#2040a0"},
                   "pattern": {"type": "spots", "intensity": 0.5}, "detail_level": "high"})


@pytest.mark.parametrize("text", [
    GOOD,
    f"Claro! Aqui está:\n```json\n{GOOD}\n```\nEspero ter ajudado.",
    f"<think>vou pensar {{ não é json }}</think>{GOOD}",
    '{"species": "t_rex", "name": "chave } dentro { do texto"}',
])
def test_extract_json_variants(text):
    obj = extract_json(text)
    assert obj["species"] == "t_rex"


@pytest.mark.parametrize("text", ["sem json", '{"species": "t_rex"', "[1, 2]", "{'species': 't_rex'}"])
def test_extract_json_failures(text):
    with pytest.raises(JSONExtractionError):
        extract_json(text)


def test_json_complete():
    assert not json_complete('{"a": {"b": 1}')
    assert json_complete('{"a": {"b": 1}} resto')


def test_examples_in_prompt_are_valid():
    for _text, answer in EXAMPLES:
        assert validate_spec(answer) == []
    msgs = build_messages("um T-rex roxo")
    assert msgs[0]["role"] == "system" and msgs[-1]["content"].endswith("um T-rex roxo")


def test_interpret_success(fake_llm_factory):
    llm = fake_llm_factory([GOOD])
    res = interpret("Um T-rex azul com manchas, muito detalhado", llm, seed=3)
    assert res.ok and res.spec["colors"]["primary"] == "#2040a0"
    assert res.spec["proportions"]["head_size"] == 1.0  # padrão
    assert "colors.primary" in res.provided_fields
    assert len(res.attempts) == 1
    assert llm.calls[0]["seed"] == 3
    info = res.info_for_config()
    assert info["validated_ai_json"]["name"] == "Rex azul"
    assert "proportions.head_size" in info["fields_from_defaults"]


def test_interpret_repairs_after_validation_error(fake_llm_factory):
    bad = json.dumps({"species": "t_rex", "proportions": {"head_size": 3.0}})
    llm = fake_llm_factory([bad, GOOD])
    res = interpret("cabeça gigante", llm)
    assert res.ok and len(res.attempts) == 2
    assert res.attempts[0]["errors"]
    repair_prompt = llm.calls[1]["messages"][-1]["content"]
    assert "proportions.head_size" in repair_prompt


def test_interpret_fails_cleanly(fake_llm_factory):
    llm = fake_llm_factory(["não sei", "{quebrado", '{"species": "raptor"}'])
    res = interpret("algo", llm, max_attempts=3)
    assert not res.ok and res.spec is None
    assert len(res.attempts) == 3 and res.errors
    err_llm = fake_llm_factory([RuntimeError("CUDA out of memory")])
    res2 = interpret("algo", err_llm)
    assert not res2.ok and "CUDA" in res2.errors[0]
    assert not interpret("   ", fake_llm_factory([])).ok


def test_semantic_warnings(fake_llm_factory):
    res = interpret("um triceratops verde", fake_llm_factory([GOOD]))
    assert res.ok
    assert any("triceratops" in w for w in res.warnings)
    assert any("verde" in w for w in res.warnings)


def test_no_eval_or_exec_in_package():
    root = os.path.join(os.path.dirname(__file__), "..", "ninho_studio")
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(dirpath, fname), encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in ("eval", "exec", "compile"), (fname, node.lineno)


def test_warns_when_example_is_copied(fake_llm_factory):
    from ninho_studio.ai.prompt import EXAMPLES

    copied = json.dumps(EXAMPLES[0][1])
    res = interpret("um T-rex azul pequeno", fake_llm_factory([copied]))
    assert res.ok and any("repetiu um exemplo" in w for w in res.warnings)
