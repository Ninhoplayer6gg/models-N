# Relatório de testes — Ninho Model Studio

Este relatório diz **exatamente** o que foi testado, como, e o que **não** pôde ser testado.

## Atualização v0.1.1 — primeiro teste real da IA (Colab, feito pelo usuário)

O usuário rodou o notebook v0.1.0 no Google Colab e enviou o `.zip` gerado
(`examples/trex-branco-ia/colab_original/tyranos_rex.json` guarda a configuração original).

| Item | Resultado registrado no `.json` |
|---|---|
| Ambiente | GPU **T4** (`cuda`, float16), transformers **5.18.0**, torch **2.11.0+cu130** |
| Modelo | Qwen/Qwen2.5-Coder-1.5B-Instruct, carregado em **33,6 s** |
| Interpretação | **11,1 s**, 277 tokens, **JSON válido na 1ª tentativa** |
| Descrição | "Um T-rex branco musculoso, cabeça grande, listras escuras nas costas, barriga creme e olhos vermelhos" |
| Acertos da IA | branco (`#ffffff`), olhos vermelhos (`#ff6347`), listras escuras (`stripes`, `#333333`), cabeça grande (`head_size` 1.4), barriga creme (`#fffbe8`, porém quase branca) |
| Erros da IA | ignorou "musculoso" (`body_bulk` ficou 1.0); copiou as proporções do 1º exemplo do prompt |

Problemas encontrados no **nosso** código (não na IA) e corrigidos na v0.1.1:

1. **Branco saía cinza:** a rampa de tons escurecia 15% por tom e a microtextura multiplicava
   as cores. Agora cores quase brancas escurecem em passos menores e com sombra fria
   (azul-acinzentada), e toda a pintura da pele trabalha por tons da paleta (ajustes de
   textura usam só 40% do caminho até o tom vizinho). O verde padrão ficou visualmente igual.
2. **Barriga sem contraste:** aviso automático quando a barriga quase não se distingue do
   corpo (contraste < 1,15), sugerindo uma cor.
3. **Textura subia para 256 sem necessidade:** novo empacotador que encaixa cubos nos cantos
   vazios do box UV (forma exata, tabela de somas acumuladas). O caso do teste (cabeça 1,4×)
   e as variantes de 42 e 46 cubos agora cabem em 128×128.
4. **IA copiando o exemplo:** exemplos do prompt trocados por descrições diferentes da
   descrição padrão do notebook (incluindo "musculoso") e nova **conferência de palavras**:
   se a descrição pede algo (musculoso, cabeça grande, cauda longa, rugindo, gigante...) que
   o JSON da IA não reflete, o notebook avisa qual controle ajustar — sem corrigir sozinho.
   *Esse novo prompt ainda não foi testado com o Qwen real.*

Verificação depois das correções: `examples/trex-branco-ia/` reconstruído a partir da resposta
da IA do Colab (sem chamar a IA de novo) abre no Blockbench 5.2.2 com 0 avisos/erros,
textura 128, ida e volta idêntica e exportação Bedrock correta (IoU 0,97/1,00/0,97).
Antes/depois em `examples/trex-branco-ia/antes_depois.png`.

## Ambiente usado

* Contêiner Linux na nuvem, **sem GPU**. Python 3.13.16, numpy 2.5, Pillow 12.3.
* Ambiente separado para a IA: **torch 2.14.1 (CPU) + transformers 5.19.0**.
* Rede restrita pela política do ambiente: **GitHub, PyPI e npm acessíveis**;
  **huggingface.co, colab.research.google.com e blockbench.net bloqueados**.
* Código do Python verificado também com a gramática do Python 3.10 e 3.11 (o Colab usa 3.12).

## 1. Testes automáticos (`pytest`)

| Ambiente | Resultado |
|---|---|
| Python do sistema (sem torch) | **124 passaram, 2 pulados** (os 2 dependem de torch/transformers) |
| Ambiente com torch + transformers | **128 passaram** |

O que cobrem:

* `test_spec.py` — esquema JSON: valores válidos/inválidos com o caminho do erro; **o
  validador interno concorda com a biblioteca oficial `jsonschema`**; ajustes manuais
  (multiplicadores, limites, cores, padrão, pele, detalhes).
* `test_uv.py` — **box UV igual aos valores gravados pelo próprio Blockbench 5.2.2**;
  orientação de cada face; empacotamento sem sobreposição e dentro do atlas.
* `test_builder.py` — hierarquia de ossos e pais; cauda com 3/4/5 segmentos afinando;
  **duas garras por mão**; mandíbula com dobradiça no fundo do crânio; **pés no chão**
  (|erro| ≤ 0,25 px) e nada abaixo de −0,3 px; pés paralelos ao chão (soma das rotações da
  perna = 0); tudo na grade de 0,5 px e 0,5°; proporções mudam a geometria; orçamento de
  elementos; determinismo por seed.
* `test_texture.py` — toda face pintada e o resto transparente; **ventre mais claro que o
  dorso** (tronco, pelve, cauda); íris e pupila nos dois lados da cabeça; céu da boca na cor
  da boca; dentes; padrões diferentes entre si e determinísticos; cores aplicadas.
* `test_bbmodel.py` — **chaves idênticas às que o Blockbench 5.2.2 grava**; outliner
  referencia cada cubo/grupo uma vez; textura embutida = PNG; `visible_box` igual ao
  `calculateVisibleBox()` do Blockbench no projeto de referência.
* `test_validate.py` — o modelo gerado não tem erros nem avisos; **erros injetados são
  detectados**: UUID duplicado/inválido, tamanho negativo, coordenada não finita, UV fora da
  textura, textura inexistente, nome de osso duplicado, cubo fora do outliner, referência
  inexistente, grupo repetido, versão errada, orçamento, UV incoerente com o box UV, face sem
  pintura, pivô longe da geometria, modelo abaixo do chão.
* `test_mesh_render.py` — malha lida do `.bbmodel` bate com o modelo; vistas renderizam; o
  olho aparece na vista lateral; folhas de imagens e visualizador HTML.
* `test_ai.py` — extração de JSON (texto em volta, cercas de código, `<think>`, chaves dentro
  de textos) e falhas; sucesso, **reparo após erro de validação**, falha limpa após N
  tentativas, exceção durante a geração, descrição vazia, avisos (pedido não suportado, cores,
  cópia do exemplo); **nenhum `eval`/`exec`/`compile` no pacote**.
* `test_ai_transformers.py` — caminho real do `transformers` com um **Qwen2 minúsculo de pesos
  aleatórios** criado localmente: carregar na CPU, chat template, gerar (greedy e com
  amostragem), parar e decodificar; resposta inválida termina em erro claro.
* `test_pipeline.py` — `.json` com descrição, parâmetros, seed e versão; **regenerar a partir
  do `.json` dá o mesmo `.bbmodel` e o mesmo `.png`**; regras de modo; textura 256 automática
  e escala reduzida com aviso quando não cabe; arquivos e `.zip`; seeds 1–3 × 3 níveis sem
  erros nem avisos; proporções extremas.
* `test_colab.py` — formulário → parâmetros; modo procedural completo; **modo IA sem modelo
  não gera nada** (não troca de modo escondido); modo IA com respostas simuladas; cache da IA
  (com criatividade 0, mudar só a seed não chama a IA de novo); downloads fora do Colab.
* `test_notebook.py` — estrutura das 5 etapas; **código embutido idêntico ao código-fonte**;
  campos do formulário; **execução real do notebook num kernel Jupyter** (via `nbclient`):
  modo procedural de ponta a ponta e modo IA com modelo que falha (mensagem de erro, nada
  gerado).

## 2. Verificação no Blockbench real

* **Blockbench 5.2.2**, código oficial (`JannisX11/blockbench`, commit `7c92e27`), compilado
  localmente com `node build.js --target=web`, servido em `127.0.0.1` e aberto num Chromium
  sem tela (Playwright 1.56.1, WebGL por SwiftShader). Ferramenta: `tools/blockbench_check.mjs`.
* **Exemplo T-rex verde** (`examples/trex-verde/blockbench/`):
  * abriu como **`bedrock`**, 32 cubos, 22 grupos, textura 128×128 carregada;
  * **validador interno do Blockbench: 0 avisos e 0 erros**; nenhuma caixa de mensagem; nenhum
    erro de console depois de abrir;
  * reabrir e salvar de novo (`Codecs.project.compile`) **não mudou** cubos, UVs, grupos nem
    a hierarquia;
  * **exportação Bedrock pelo próprio Blockbench** funcionou (`geometry.trex_verde`, 22 ossos,
    32 cubos, `trex_verde.geo.json`);
  * `visible_box` gravado = o calculado pelo Blockbench (`[7, 3.5, 1.25]`);
  * capturas de 5 ângulos; **IoU das silhuetas** (Blockbench × prévia do Ninho):
    lado 0,981 · frente 0,978 · topo 0,989 (as diferenças são bordas de 1 px);
  * **articulações:** uma pose de teste (mandíbula, pescoço, cabeça, pernas, canela, cauda,
    braço e antebraço) aplicada dentro do Blockbench move cada parte em torno do pivô certo,
    sem peças soltas; a mesma pose na prévia do Ninho dá IoU 0,985
    (`comparacao_pose.png`).
* **9 variantes** (galeria, 3 níveis de detalhe, textura 256, espinhos, chifres, penas,
  cicatrizes e o caso branco com cabeça 1,4×): todas com 0 avisos/erros do validador do
  Blockbench, ida e volta idêntica, exportação Bedrock correta e IoU entre 0,96 e 1,00
  (`docs/verificacao-blockbench-variantes.json`, gerado por `tools/verify_variants.py`).
* Inspeção visual feita por mim nas capturas: geometria, textura nas faces certas (olhos nas
  laterais, ventre claro embaixo, boca vermelha, dentes, dedos) e postura iguais à prévia.

**Limitação:** foi a **build web** do Blockbench (mesmo código do aplicativo), não o
aplicativo de desktop nem o `web.blockbench.net` (bloqueado aqui), e não foi aberto num
celular.

## 3. Visualizador 3D

`*_3d.html` aberto num Chromium emulando celular (412×915, toque): carregou o WebGL sem erros,
arrastar gira, botões *3/4, Frente, Lado, Topo, Girar, Ossos* funcionam, enquadramento correto
em tela retrato. O mesmo visualizador dentro de um `<iframe srcdoc>` (forma usada na saída do
notebook) também carregou e respondeu aos botões. **Não** foi testado num Android real nem
dentro da saída do Colab.

## 4. O que NÃO foi testado

* **O Qwen real neste ambiente de desenvolvimento** (Hugging Face bloqueado). A IA real foi
  rodada **uma vez, pelo usuário, no Colab** (seção de atualização acima): um único caso não mede
  a taxa de acerto. O prompt novo da v0.1.1 ainda não rodou com o Qwen real. Próximo passo:
  10–20 descrições variadas, anotando acertos e erros.
* **Partes do Colab que o teste do usuário não registra:** o `.zip` mostra que as Etapas 1 a 5
  funcionaram (inclusive o download), mas não diz como ficaram os formulários no celular, se o
  visualizador 3D abriu na saída do Colab, nem o comportamento com o Google Drive e os limites
  de sessão.
* **Minecraft.** O `.geo.json` exportado pelo Blockbench não foi carregado no jogo.

## 5. Exemplo T-rex verde

* Gerado no **modo procedural** (parâmetros escritos à mão), seed 42, textura 128, orçamento
  64 — *não* pela IA, pelo motivo acima. Reproduzível com `python tools/make_example.py`
  (mesmos bytes de `.bbmodel` e `.png`).
* 32 cubos, 22 ossos, 75% da área do atlas reservada (51% em pixels de faces), validação do
  Ninho sem erros nem avisos.
* Geração: ~0,05–0,07 s; arquivos + prévias: ~0,3 s (CPU deste ambiente).
