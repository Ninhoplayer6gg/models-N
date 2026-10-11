"""Gera o notebook Ninho-Model-Studio.ipynb com o pacote ninho_studio embutido.

O código vai dentro da Etapa 1 como um .zip em base64 com verificação
SHA-256. Assim o notebook funciona sozinho no Colab (aberto pelo GitHub, pelo
Drive ou por upload), sem clonar repositório e sem servidor externo.

Uso:  python tools/build_notebook.py   (rode de novo sempre que mudar o código)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "ninho_studio")
NOTEBOOK = os.path.join(ROOT, "Ninho-Model-Studio.ipynb")


def package_zip() -> bytes:
    """Zip determinístico com os .py do pacote (mesmo código = mesmos bytes)."""
    files = []
    for dirpath, dirnames, filenames in os.walk(PACKAGE):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".py"):
                full = os.path.join(dirpath, name)
                files.append((os.path.relpath(full, ROOT).replace(os.sep, "/"), full))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, full in sorted(files):
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as fh:
                zf.writestr(info, fh.read())
    return buf.getvalue()


def md(cell_id: str, text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {"id": cell_id}, "source": text.strip("\n").splitlines(keepends=True)}


def code(cell_id: str, text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"cellView": "form", "id": cell_id},
        "outputs": [],
        "source": text.strip("\n").splitlines(keepends=True),
    }


INTRO = """
# 🦖 Ninho Model Studio — protótipo v0.1

Gera **modelos 3D estilo Minecraft** como projeto editável do **Blockbench** (`.bbmodel`) a partir de uma descrição.
Uma **IA de pesos abertos**, rodando aqui mesmo no Colab, transforma o pedido em dados estruturados; um
**construtor procedural** monta cubos, ossos (grupos), pivôs, UV e a textura.

**Como usar pelo celular**
1. *(Opcional, deixa a IA rápida)* menu **Ambiente de execução → Alterar o tipo de ambiente de execução → T4 GPU**.
2. Toque no ▶ de cada etapa **em ordem** e espere aparecer ✅.
3. Na **Etapa 3** escreva a descrição e ajuste os controles; toque ▶ na **Etapa 3** e depois ▶ na **Etapa 4**.
   Sempre que mudar algo na Etapa 3, execute a Etapa 3 e a Etapa 4 de novo (não precisa repetir as Etapas 1 e 2).
4. Na **Etapa 5** baixe o `.zip` com o `.bbmodel`, a textura `.png` e a configuração `.json`.

| Modo | Quem decide os parâmetros |
|---|---|
| **IA (descrição livre)** | O modelo de linguagem da Etapa 2 lê a descrição e devolve um JSON, que só é aceito se passar no esquema. |
| **Procedural (parâmetros manuais)** | Ninguém “interpreta” nada: valem só os controles da Etapa 3. |

> A **textura é sempre procedural** (regras + seed), não é desenhada pela IA.
> O `.bbmodel` é o projeto **editável**; para usar no Minecraft, abra no Blockbench e exporte
> (ex.: *File → Export → Export Bedrock Geometry*). Exportadores GeckoLib/Java ficam para depois.
"""

STEP1 = """
#@title 1️⃣ Preparar o ambiente { display-mode: "form" }
#@markdown Instala o Ninho Model Studio nesta sessão (leva alguns segundos). Execute sempre que abrir ou reiniciar o Colab.
import base64, hashlib, io, os, sys, zipfile
_PACOTE = "__PACKAGE__"
_SHA256 = "__SHA256__"
_BASE = "/content" if os.path.isdir("/content") else os.getcwd()
_DESTINO = os.path.join(_BASE, "ninho_model_studio")
_dados = base64.b64decode(_PACOTE)
if hashlib.sha256(_dados).hexdigest() != _SHA256:
    raise RuntimeError("O código embutido no notebook está corrompido. Baixe o notebook de novo.")
with zipfile.ZipFile(io.BytesIO(_dados)) as _z:
    _z.extractall(_DESTINO)
if _DESTINO not in sys.path:
    sys.path.insert(0, _DESTINO)
for _m in [m for m in list(sys.modules) if m == "ninho_studio" or m.startswith("ninho_studio.")]:
    del sys.modules[_m]
from ninho_studio import colab as studio
AMBIENTE = studio.preparar_ambiente()
"""

AI_NOTES = """
### Sobre a IA (Etapa 2)
* Modelo recomendado: **Qwen2.5-Coder-1.5B-Instruct**, licença **Apache-2.0**, baixado do Hugging Face **sem chave de API**
  (~3 GB na primeira vez de cada sessão). Ele roda dentro do Colab; não usa a IA integrada do Google.
* Com GPU T4: alguns segundos por descrição. Só com CPU: de 1 a 3 minutos (ou escolha o **0.5B**, mais rápido e menos preciso).
* Um aviso sobre `HF_TOKEN` pode aparecer: ignore, modelos públicos não precisam de token.
* Se a IA falhar, a mensagem mostra o motivo. Você pode usar o **modo procedural** na Etapa 3 — o notebook nunca troca
  de modo sozinho.
* **Pule esta etapa** se for usar só o modo procedural.
"""

STEP2 = """
#@title 2️⃣ Carregar a IA (opcional) { display-mode: "form" }
#@markdown Escolha o modelo (pode digitar outro nome do Hugging Face) e onde rodar.
modelo = "Qwen/Qwen2.5-Coder-1.5B-Instruct" #@param ["Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct"] {allow-input: true}
dispositivo = "automático" #@param ["automático", "GPU", "CPU"]
LLM = studio.carregar_ia(modelo, dispositivo)
"""

STEP3 = """
#@title 3️⃣ Descrição e parâmetros { display-mode: "form" }
#@markdown **Modo** — *IA* interpreta a descrição; *Procedural* usa só os controles abaixo.
modo = "IA (descrição livre)" #@param ["IA (descrição livre)", "Procedural (parâmetros manuais)"]
descricao = "Um T-rex verde musculoso, cabeça grande, listras escuras nas costas, barriga creme e olhos amarelos" #@param {type:"string"}
nome = "" #@param {type:"string"}
#@markdown ---
#@markdown **Proporções** — 1.0 = sem mudança. No modo IA, multiplicam o valor escolhido pela IA.
cabeca = 1.0 #@param {type:"slider", min:0.6, max:1.6, step:0.05}
focinho = 1.0 #@param {type:"slider", min:0.6, max:1.6, step:0.05}
pescoco = 1.0 #@param {type:"slider", min:0.6, max:1.6, step:0.05}
tronco_comprimento = 1.0 #@param {type:"slider", min:0.7, max:1.4, step:0.05}
tronco_volume = 1.0 #@param {type:"slider", min:0.7, max:1.4, step:0.05}
bracos = 1.0 #@param {type:"slider", min:0.5, max:1.8, step:0.05}
pernas_comprimento = 1.0 #@param {type:"slider", min:0.7, max:1.4, step:0.05}
pernas_espessura = 1.0 #@param {type:"slider", min:0.7, max:1.4, step:0.05}
cauda_comprimento = 1.0 #@param {type:"slider", min:0.6, max:1.6, step:0.05}
cauda_espessura = 1.0 #@param {type:"slider", min:0.7, max:1.4, step:0.05}
escala = 1.0 #@param {type:"slider", min:0.6, max:1.6, step:0.05}
boca = "automática" #@param ["automática", "fechada", "entreaberta", "aberta", "rugindo"]
#@markdown ---
#@markdown **Cores** — escreva `#rrggbb` (ex.: `#4f7a35`) ou deixe `auto`.
cor_principal = "auto" #@param {type:"string"}
cor_secundaria = "auto" #@param {type:"string"}
cor_barriga = "auto" #@param {type:"string"}
cor_padrao = "auto" #@param {type:"string"}
cor_olhos = "auto" #@param {type:"string"}
#@markdown ---
#@markdown **Aparência e detalhes** — “automático” mantém o que a IA (ou o padrão) escolheu.
padrao = "automático" #@param ["automático", "nenhum", "listras", "manchas", "faixas", "mosqueado"]
intensidade_padrao = "automática" #@param ["automática", "suave", "média", "forte"]
pele = "automática" #@param ["automática", "escamas", "rugosa", "lisa", "penas"]
detalhe = "automático" #@param ["automático", "baixo", "médio", "alto"]
chifres = "automático" #@param ["automático", "sim", "não"]
espinhos = "automático" #@param ["automático", "sim", "não"]
dentes = "automático" #@param ["automático", "sim", "não"]
cicatrizes = "automático" #@param ["automático", "sim", "não"]
crista_penas = "automático" #@param ["automático", "sim", "não"]
#@markdown ---
#@markdown **Técnico** — textura 128 ou 256 px, limite de cubos e seed (mesma seed = mesmo resultado).
textura = "128" #@param ["128", "256"]
orcamento_elementos = 64 #@param {type:"slider", min:16, max:128, step:4}
seed = 42 #@param {type:"integer"}
#@markdown **IA** (só no modo IA) — criatividade 0 = sempre a mesma resposta para a mesma descrição.
criatividade_ia = 0.0 #@param {type:"slider", min:0, max:1, step:0.1}
tentativas_ia = 3 #@param {type:"slider", min:1, max:4, step:1}
refazer_interpretacao = False #@param {type:"boolean"}
PARAMS = studio.coletar_parametros(**{_k: globals()[_k] for _k in studio.CAMPOS_FORMULARIO})
"""

STEP4 = """
#@title 4️⃣ Gerar e visualizar { display-mode: "form" }
#@markdown Usa os parâmetros salvos na **Etapa 3**. Mostra as vistas (frente, lado, topo, perspectiva...), o atlas UV,
#@markdown o esqueleto com os pivôs e um visualizador 3D (arraste para girar, dois dedos para aproximar).
visualizador_3d = True #@param {type:"boolean"}
mostrar_atlas = True #@param {type:"boolean"}
mostrar_esqueleto = True #@param {type:"boolean"}
RESULTADO = studio.gerar_e_mostrar(globals().get("PARAMS"), llm=globals().get("LLM"), visualizador_3d=visualizador_3d,
                                   mostrar_atlas=mostrar_atlas, mostrar_esqueleto=mostrar_esqueleto)
"""

STEP5 = """
#@title 5️⃣ Baixar os arquivos { display-mode: "form" }
#@markdown O `.zip` traz o `.bbmodel` (Blockbench), a textura `.png`, a configuração `.json`, as imagens e o visualizador `.html`.
o_que_baixar = "pacote .zip" #@param ["pacote .zip", "só o .bbmodel", "só a textura .png", "só o .json", "todos separados"]
copiar_para_o_google_drive = False #@param {type:"boolean"}
studio.baixar_arquivos(o_que_baixar, copiar_para_drive=copiar_para_o_google_drive)
"""

HELP = """
### Problemas comuns
* **“A IA não carregou” / falta de memória** — use o modelo 0.5B, ou *Ambiente de execução → Reiniciar sessão* e rode a
  Etapa 1 de novo. Enquanto isso, o modo procedural funciona.
* **A IA devolveu algo inválido** — o erro aparece com a resposta da IA. Tente outra seed, simplifique a descrição ou use o
  modo procedural.
* **A sessão do Colab caiu** (inatividade ou limite do plano gratuito) — os arquivos em `/content` somem; rode as etapas de
  novo ou marque *copiar para o Google Drive* na Etapa 5.
* **O download não começou** — toque nos botões verdes que aparecem na Etapa 5.
* **Abrir no Blockbench pelo celular** — acesse `web.blockbench.net` → *File → Open Model* e escolha o `.bbmodel`.
* A criatura olha para **-Z (norte)**, com o lado direito em **+X** e os pés em **Y = 0** (16 px = 1 bloco).
"""


def build() -> dict:
    data = package_zip()
    b64 = base64.b64encode(data).decode("ascii")
    sha = hashlib.sha256(data).hexdigest()
    cells = [
        md("intro", INTRO),
        code("etapa1", STEP1.replace("__PACKAGE__", b64).replace("__SHA256__", sha)),
        md("sobre_ia", AI_NOTES),
        code("etapa2", STEP2),
        code("etapa3", STEP3),
        code("etapa4", STEP4),
        code("etapa5", STEP5),
        md("ajuda", HELP),
    ]
    return {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": [], "toc_visible": True, "name": "Ninho-Model-Studio.ipynb", "gpuType": "T4"},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
        },
        "cells": cells,
    }


def main() -> None:
    nb = build()
    with open(NOTEBOOK, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"notebook gerado: {NOTEBOOK} ({os.path.getsize(NOTEBOOK) // 1024} KB)")


if __name__ == "__main__":
    main()
