# Ferramentas de desenvolvimento

Não são necessárias para usar o notebook; servem para manter e verificar o projeto.

| Ferramenta | Para quê |
|---|---|
| `build_notebook.py` | Gera `Ninho-Model-Studio.ipynb` com o pacote `ninho_studio` embutido. **Rode sempre que mudar o código** (um teste falha se o notebook estiver desatualizado). |
| `make_example.py` | Gera `examples/trex-verde/`, reconstrói `examples/trex-branco-ia/` a partir do `.json` do Colab (sem chamar a IA) e gera `docs/img/variacoes.png`. |
| `blockbench_check.mjs` | Abre um `.bbmodel` no Blockbench oficial (build web local) e registra validador, capturas, ida e volta, exportação Bedrock e `visible_box`. |
| `compare_renders.py` | IoU das silhuetas entre as capturas do Blockbench e a prévia do Ninho; opcionalmente gera a imagem lado a lado e compara a pose de teste (`--pose pose.json saida.png`). |
| `verify_variants.py` | Gera 9 variantes, abre cada uma no Blockbench e grava `docs/verificacao-blockbench-variantes.json`. |
| `geo_check.mjs` | Abre um `.bbmodel` no Blockbench, compara a exportação Bedrock dele com o nosso `.geo.json` e reabre o `.geo.json` sozinho (com o `.png`) para comparar ossos, cubos, UV e capturas. |
| `verify_geckolib.py` | Roda o `geo_check.mjs` nos 2 exemplos, nas 9 variantes e num caso sintético (cubo girado/espelhado/inflado) e grava `docs/verificacao-geckolib.json`. |
| `geckolib_loader_check.py` + `geckolib_check/` | Compila os **leitores de geometria do GeckoLib 4 e 5** a partir do código-fonte (com substitutos mínimos das classes do Minecraft em `geckolib_check/stubs`), carrega os mesmos 12 `.geo.json`, confere cada canto de face (posição + UV) contra o Blockbench e roda um controle negativo. Grava `docs/verificacao-geckolib-leitor.json`. |

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

Conferência do `.geo.json` (GeckoLib) no Blockbench, com a mesma build web servida:

```bash
python tools/verify_geckolib.py --playwright /caminho/para/playwright/index.mjs
```

## Conferir com os leitores do GeckoLib (precisa de JDK 21+ e git)

Baixe para uma pasta os `.jar` do Maven Central: `gson` (2.11 ou mais nova), `guava`,
`fastutil`, `jspecify`, `org.jetbrains:annotations` e `joml`. Depois:

```bash
python tools/geckolib_loader_check.py --lib pasta_dos_jars
```

O script baixa o GeckoLib do GitHub nos commits testados (ou use `--geckolib5`/`--geckolib4`
com um checkout local).
