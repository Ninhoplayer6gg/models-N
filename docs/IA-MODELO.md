# A IA do Ninho Model Studio

## O que a IA faz (e o que não faz)

| Etapa | Quem faz |
|---|---|
| Ler a descrição livre e devolver **dados estruturados** (JSON) | **IA** (modelo de linguagem local) — só no modo IA |
| Validar o JSON contra o esquema | Código (mesmo validador do modo procedural) |
| Montar cubos, ossos, pivôs, UV | Construtor procedural (`ninho_studio/builders/theropod.py`) |
| Pintar a textura | Regras procedurais + seed (`ninho_studio/texture.py`) |

O notebook mostra sempre de onde vieram os parâmetros ("IA + construtor procedural" ou
"procedural (sem IA)"). Se a IA falhar, aparece o erro e a sugestão de usar o modo
procedural — **nunca** há troca silenciosa de modo.

## Modelo escolhido: Qwen2.5-Coder-1.5B-Instruct

| Critério | Situação |
|---|---|
| Licença | **Apache-2.0** (página oficial `Qwen/Qwen2.5-Coder-1.5B-Instruct` no Hugging Face). Atenção: na mesma família, o **3B** usa a licença *Qwen Research*; os tamanhos 0.5B e 1.5B são Apache-2.0. |
| Pesos abertos / sem chave | Sim. Download público do Hugging Face, sem token; roda dentro do Colab. Não usa a IA integrada do Google nem APIs pagas. |
| Arquitetura | Qwen2 (`Qwen2ForCausalLM`), suportada pelo `transformers` desde a 4.37; o Colab já traz versões mais novas. |
| Tamanho | ~1,5 bilhão de parâmetros; ~3,1 GB de download (bf16). |
| GPU (T4 do Colab) | carregado em float16 (~3,5 GB de VRAM, estimativa). |
| CPU (sem GPU) | carregado em float32 (~6,2 GB de RAM, estimativa; o Colab gratuito tem ~12 GB). Funciona, porém lento. |
| Alternativas no notebook | `Qwen/Qwen2.5-Coder-0.5B-Instruct` (Apache-2.0, mais rápido na CPU, erra mais) e `Qwen/Qwen2.5-1.5B-Instruct` (Apache-2.0, uso geral). O campo aceita digitar outro modelo. |

Os números de memória e velocidade acima são **estimativas** a partir do tamanho do modelo:
neste ambiente de desenvolvimento o acesso ao Hugging Face estava bloqueado e os pesos reais
não puderam ser baixados (ver [RELATORIO-DE-TESTES.md](RELATORIO-DE-TESTES.md)).

### Compatibilidade de código

* `ninho_studio/ai/llm.py` usa `AutoTokenizer`/`AutoModelForCausalLM`, `apply_chat_template`,
  `GenerationConfig` e um critério de parada que encerra a geração assim que o objeto JSON
  fecha (economiza tempo na CPU).
* Funciona com `transformers` 4.x e 5.x: usa o argumento `dtype` a partir da 4.56 e
  `torch_dtype` antes disso.
* Testado com **transformers 5.19.0 + torch 2.14.1 (CPU)** usando um Qwen2 minúsculo de
  pesos aleatórios criado localmente (`tests/tiny_qwen.py`) — isso exercita o mesmo caminho de
  código (carregar, chat template, gerar, parar, decodificar), mas não mede a qualidade.

## Como a saída da IA é controlada

1. **Prompt** (`ninho_studio/ai/prompt.py`): instruções curtas em inglês (modelos pequenos
   seguem melhor), o esquema com intervalos, dicas de vocabulário em português
   ("cabeça enorme → head_size 1.3–1.5", "listras → stripes"...) e dois exemplos completos.
2. **Decodificação determinística** por padrão (criatividade 0 = greedy). Com criatividade > 0
   há amostragem com `torch.manual_seed(seed)`.
3. **Extração sem `eval`/`exec`** (`ninho_studio/ai/extract.py`): encontra o primeiro objeto
   `{...}` com chaves balanceadas, respeitando textos entre aspas, e lê com `json.loads`.
   Um teste varre o pacote e falha se aparecer `eval`, `exec` ou `compile`.
4. **Validação pelo esquema** (`ninho_studio/spec.py`): JSON Schema draft 2020-12 com tipos,
   intervalos, enumerações, cores `#rrggbb` e chaves desconhecidas proibidas. O validador
   interno é conferido contra a biblioteca oficial `jsonschema` nos testes.
5. **Reparo:** se falhar, a IA recebe a lista de erros e tenta de novo (até 3 tentativas,
   configurável). Se nenhuma passar, o resultado é `ok=False` com os erros e a última resposta.
6. **Avisos informativos** (não bloqueiam): a IA repetiu um exemplo do prompt; preencheu
   poucos campos; a descrição pede algo que esta versão não constrói (ex.: "triceratops");
   palavras da descrição que o JSON não refletiu (musculoso, cabeça grande, cauda longa,
   rugindo, gigante, filhote...); cores citadas × cores geradas (com nome aproximado).

### Esquema (resumo)

| Campo | Valores |
|---|---|
| `species` | `"t_rex"` (obrigatório) |
| `name` | texto, até 40 caracteres |
| `scale` | 0.6 – 1.6 |
| `proportions.*` | `head_size`, `snout_length`, `neck_length`, `tail_length` 0.6–1.6; `body_length`, `body_bulk`, `leg_length`, `leg_thickness`, `tail_thickness` 0.7–1.4; `arm_length` 0.5–1.8; `jaw_open` 0–1 |
| `colors.*` | `primary`, `secondary`, `belly`, `pattern`, `eyes`, `claws`, `mouth` em `#rrggbb` |
| `pattern` | `type`: `none`, `stripes`, `spots`, `bands`, `mottled`; `intensity` 0–1 |
| `skin` | `scales`, `rough`, `smooth`, `feathered` |
| `features.*` | `brow_horns`, `back_spikes`, `teeth_visible`, `scars`, `feather_crest` (true/false) |
| `detail_level` | `low`, `medium`, `high` |

Campos ausentes recebem o padrão do T-rex verde. O JSON completo está em
`ninho_studio.spec.json_schema()`.

## Primeiro teste real (Colab, GPU T4)

Feito pelo usuário com a v0.1.0: modelo carregado em 33,6 s; interpretação em 11,1 s;
**JSON válido na 1ª tentativa**. A IA acertou branco, olhos vermelhos, listras escuras e
cabeça grande, mas ignorou "musculoso" e repetiu as proporções do primeiro exemplo do prompt
(que era parecido demais com a descrição padrão do notebook). Na v0.1.1:

* os exemplos do prompt foram trocados por descrições diferentes da descrição padrão, e um
  deles mostra "musculoso → body_bulk 1.3";
* a **conferência de palavras** (`keyword_checks`) compara a descrição com o JSON e avisa,
  por exemplo: *"A descrição pede um corpo musculoso/robusto, mas a IA deixou
  proportions.body_bulk = 1.0. Se quiser, ajuste tronco_volume (ex.: 1.25) na Etapa 3."*
  Nada é corrigido sozinho: o resultado continua sendo o da IA e o aviso diz o que mudar.

## Limites do Colab gratuito

O FAQ do Colab informa que os recursos gratuitos **não são garantidos**, que os limites
(tempo de sessão, inatividade, GPU) variam e não são publicados, e que o Colab prioriza quem
está usando o notebook de forma interativa; interfaces web que substituem o notebook para
geração de conteúdo costumam ter a sessão encerrada no plano gratuito. Por isso o Ninho usa
só formulários e saídas nativas do próprio notebook — sem servidor, túnel ou interface
externa. Fonte: [Colab FAQ](https://research.google.com/colaboratory/faq.html).
