import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def default_result():
    from ninho_studio.pipeline import generate
    from ninho_studio.spec import BuildSettings, default_spec

    spec = default_spec()
    spec["name"] = "T-rex teste"
    return generate(spec, BuildSettings(seed=42), mode="procedural", description="teste")


class FakeLLM:
    """Gerador de texto falso: devolve respostas pré-definidas, na ordem."""

    model_id = "fake/llm"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, messages, max_new_tokens=700, temperature=0.0, seed=0, stop_when_json_complete=True):
        self.calls.append({"messages": messages, "temperature": temperature, "seed": seed})
        reply = self.replies.pop(0) if self.replies else ""
        if isinstance(reply, Exception):
            raise reply

        class Out:
            text = reply
            new_tokens = len(reply.split())
            seconds = 0.01

        return Out()

    def describe(self):
        return {"model_id": self.model_id, "device": "cpu", "dtype": "float32", "license": "teste"}


@pytest.fixture
def fake_llm_factory():
    return FakeLLM
