"""Testes do notebook: estrutura, código embutido atualizado e execução real num kernel Jupyter."""

import base64
import hashlib
import importlib.util
import os
import re

import pytest

nbformat = pytest.importorskip("nbformat")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB_PATH = os.path.join(ROOT, "Ninho-Model-Studio.ipynb")


def _builder():
    spec = importlib.util.spec_from_file_location("build_notebook", os.path.join(ROOT, "tools", "build_notebook.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load():
    nb = nbformat.read(NB_PATH, as_version=4)
    nbformat.validate(nb)
    return nb


def test_structure_and_titles():
    nb = _load()
    code = [c for c in nb.cells if c.cell_type == "code"]
    titles = [c.source.splitlines()[0] for c in code]
    for i, title in enumerate(titles, start=1):
        assert title.startswith(f"#@title {i}\ufe0f\u20e3"), title  # 1️⃣ ... 5️⃣
    assert len(code) == 5
    assert ["Preparar o ambiente" in titles[0], "Carregar a IA" in titles[1], "Descrição e parâmetros" in titles[2],
            "Gerar e visualizar" in titles[3], "Baixar os arquivos" in titles[4]] == [True] * 5
    assert all(c.metadata.get("cellView") == "form" for c in code)
    assert "Como usar pelo celular" in nb.cells[0].source
    assert nb.metadata["accelerator"] == "GPU"


def test_embedded_code_is_current():
    nb = _load()
    src = nb.cells[1].source
    b64 = re.search(r'_PACOTE = "([^"]+)"', src).group(1)
    sha = re.search(r'_SHA256 = "([0-9a-f]+)"', src).group(1)
    data = base64.b64decode(b64)
    assert hashlib.sha256(data).hexdigest() == sha
    assert data == _builder().package_zip(), "rode: python tools/build_notebook.py"


def test_form_fields_match_helper():
    from ninho_studio.colab import CAMPOS_FORMULARIO

    src = _load().cells[4].source
    names = re.findall(r"^(\w+) = .*#@param", src, flags=re.M)
    assert tuple(names) == CAMPOS_FORMULARIO


def _run(nb, cwd, timeout=900):
    nbclient = pytest.importorskip("nbclient")
    client = nbclient.NotebookClient(nb, timeout=timeout, kernel_name="python3", resources={"metadata": {"path": str(cwd)}})
    client.execute()
    return nb


def _text(cell):
    out = []
    for o in cell.get("outputs", []):
        if "text" in o:
            out.append(o["text"])
        data = o.get("data", {})
        out.append(data.get("text/html", "") if isinstance(data.get("text/html", ""), str) else "".join(data["text/html"]))
        out.append(data.get("text/plain", "") if isinstance(data.get("text/plain", ""), str) else "".join(data["text/plain"]))
    return "\n".join(out)


def test_execute_procedural_mode(tmp_path):
    pytest.importorskip("ipykernel")
    nb = _load()
    nb.cells[3].source = 'LLM = studio.carregar_ia("/caminho/que/nao/existe", "CPU")'
    nb.cells[4].source = nb.cells[4].source.replace(
        'modo = "IA (descrição livre)"', 'modo = "Procedural (parâmetros manuais)"')
    _run(nb, tmp_path)
    assert "Ambiente pronto" in _text(nb.cells[1])
    assert "A IA não carregou" in _text(nb.cells[3])
    assert "Parâmetros salvos" in _text(nb.cells[4])
    out4 = _text(nb.cells[5])
    assert "Modelo gerado" in out4 and "Validação sem erros" in out4 and "procedural (sem IA)" in out4
    assert "image/png" in str(nb.cells[5].outputs)
    assert "nms-wrap" in out4  # visualizador 3D
    assert "Seus arquivos" in _text(nb.cells[6])
    saida = tmp_path / "ninho_saida"
    names = {p.name for p in saida.iterdir()}
    assert any(n.endswith(".bbmodel") for n in names) and any(n.endswith(".zip") for n in names)


def test_execute_ai_mode_with_failing_model(tmp_path):
    pytest.importorskip("ipykernel")
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from tiny_qwen import make_tiny_qwen

    tiny = make_tiny_qwen(str(tmp_path / "tiny"))
    nb = _load()
    nb.cells[3].source = f'LLM = studio.carregar_ia({tiny!r}, "CPU")'
    nb.cells[4].source = nb.cells[4].source.replace("tentativas_ia = 3", "tentativas_ia = 1")
    _run(nb, tmp_path)
    assert "IA carregada" in _text(nb.cells[3])
    out4 = _text(nb.cells[5])
    assert "A IA não produziu um JSON válido" in out4
    assert "Modelo gerado" not in out4  # não troca para o procedural escondido
    assert "Nada para baixar" in _text(nb.cells[6])
