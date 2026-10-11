# Ferramentas de desenvolvimento

Não são necessárias para usar o notebook; servem para manter e verificar o projeto.

| Ferramenta | Para quê |
|---|---|
| `build_notebook.py` | Gera `Ninho-Model-Studio.ipynb` com o pacote `ninho_studio` embutido. **Rode sempre que mudar o código** (um teste falha se o notebook estiver desatualizado). |
| `make_example.py` | Gera `examples/trex-verde/` e `docs/img/variacoes.png`. |
| `blockbench_check.mjs` | Abre um `.bbmodel` no Blockbench oficial (build web local) e registra validador, capturas, ida e volta, exportação Bedrock e `visible_box`. |
| `compare_renders.py` | IoU das silhuetas entre as capturas do Blockbench e a prévia do Ninho; opcionalmente gera a imagem lado a lado. |

## Testes

```bash
python -m pytest -q                      # sem torch: pula os 2 testes do transformers
pip install torch transformers nbclient ipykernel   # para rodar tudo
```

## Verificar no Blockbench (computador com Node 20+)

```bash
git clone --depth 1 https://github.com/JannisX11/blockbench.git
cd blockbench
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts
node build.js --target=web
python3 -m http.server 8765 --bind 127.0.0.1 &      # serve a build web
cd ../models-N
node tools/blockbench_check.mjs --model examples/trex-verde/trex_verde.bbmodel --out /tmp/check \
     --pose examples/trex-verde/blockbench/pose_teste.json \
     --playwright /caminho/para/playwright/index.mjs
python tools/compare_renders.py examples/trex-verde/trex_verde.bbmodel /tmp/check /tmp/check/lado_a_lado.png
```

O relatório fica em `/tmp/check/blockbench_report.json`.
