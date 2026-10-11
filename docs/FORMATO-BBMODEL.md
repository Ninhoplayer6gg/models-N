# Formato do arquivo `.bbmodel` gerado

## Versão e formato escolhidos

| Item | Valor | Onde foi conferido |
|---|---|---|
| Blockbench de referência | **5.2.2** (código oficial, commit `7c92e27`, 9 out. 2026) | `package.json` do repositório `JannisX11/blockbench` |
| `meta.format_version` | **`"5.0"`** | constante `FORMATV` em `js/formats/bbmodel.js:6` |
| `meta.model_format` | **`"bedrock"`** (Bedrock Entity) | formato `id: 'bedrock'` em `js/formats/bedrock/bedrock.js:1556` |
| `meta.box_uv` | **`true`** | o formato Bedrock usa box UV por padrão (`box_uv: true`) |

**Por que `bedrock`:** é um formato de entidade do Minecraft com ossos (grupos) e pivôs,
box UV, uma textura por modelo e rotação em qualquer ângulo — e o próprio Blockbench
exporta dele para `.geo.json` (Bedrock), base também usada pelo GeckoLib. Toda rotação do
modelo fica nos **ossos**; nenhum cubo é girado, o que também facilita converter para
formatos Java (que não giram cubos individuais).

A documentação oficial ([The .bbmodel format](https://www.blockbench.net/wiki/docs/bbmodel/),
fonte em `JannisX11/blockbench.net/content/docs/bbmodel.md`) diz que **não existe uma
especificação completa** e recomenda olhar arquivos de exemplo e o código
(`js/formats/bbmodel.js`). Por isso a estrutura foi copiada de um projeto de referência
**gerado pelo próprio Blockbench 5.2.2** (build web compilada do código-fonte e aberta num
Chromium sem tela): um grupo com rotação, um subgrupo, dois cubos em box UV e uma textura
embutida, salvo com `Codecs.project.compile()`.

## Campos gravados

Gravamos os mesmos campos que o Blockbench 5.2.2 grava nesse projeto de referência,
exceto o estado de seleção da interface (`selected`, `primary_selected`, `_static`), que o
Blockbench ignora ao abrir.

* **Raiz:** `meta`, `name`, `model_identifier`, `visible_box`, `variable_placeholders`,
  `multi_file_ruleset`, `variable_placeholder_buttons`, `bedrock_animation_mode`,
  `timeline_setups`, `unhandled_root_fields`, `resolution`, `elements`, `groups`, `outliner`,
  `textures` (propriedades de `ModelProject` em `js/io/project.ts:583-680` e `compile()` em
  `js/formats/bbmodel.js`).
* **Cubos (`elements`):** `name`, `box_uv`, `render_order`, `locked`, `export`, `scope`,
  `allow_mirror_modeling`, `from`, `to`, `autouv`, `color`, `origin`, `uv_offset`, `faces`,
  `type: "cube"`, `uuid` (`Cube.getSaveCopy` em `js/outliner/types/cube.js:344`). Cada face
  tem `uv` e `texture` — o **índice** da textura na lista, como em
  `js/outliner/abstract/face.ts:78`.
* **Grupos (`groups`):** `name`, `uuid`, `export`, `locked`, `scope`, `visibility`,
  `origin` (pivô), `rotation`, `bedrock_binding`, `color`, `children: []`, `reset`, `shade`,
  `mirror_uv`, `autouv`, `isOpen` (`Group.getSaveCopy`/propriedades em
  `js/outliner/types/group.js`).
* **Hierarquia (`outliner`):** desde o formato 5.0 os dados dos grupos ficam em `groups` e a
  árvore fica em `outliner` só com `{uuid, isOpen, children}` e UUIDs de cubos
  (`Outliner.toJSON` em `js/outliner/outliner.js:122`; nota da versão 5.0 na wiki).
* **Textura:** o PNG vai embutido (`internal: true`, `source: "data:image/png;base64,..."`)
  com `width`/`height` do PNG e `uv_width`/`uv_height` iguais à `resolution`
  (`Texture.getSaveCopy` em `js/texturing/textures.js:318`). Assim o arquivo abre sozinho no
  app ou no `web.blockbench.net`.

## Convenções conferidas no código

* **Rotação:** graus, aplicados sem inversão de sinal (`NodePreviewController.updateTransform`,
  `js/outliner/outliner.js:294`), ordem de Euler **`ZYX`** do three.js
  (`js/io/format.ts:717`), isto é, matriz `Rz·Ry·Rx`. Cada grupo gira os filhos em torno do
  próprio `origin`, em coordenadas absolutas.
* **Box UV:** layout da função `updateUV` (`js/outliner/types/cube.js:1298`): linha de cima com
  *cima* e *baixo* (espelhadas), linha de baixo com leste, norte, oeste e sul; tamanhos
  arredondados para baixo. Reproduzido em `ninho_studio/uv.py` e testado contra os valores
  gravados pelo Blockbench (`tests/test_uv.py`).
* **Qual ponto 3D cada texel cobre:** tradução de `CubeFace.UVToLocal`
  (`js/outliner/types/cube.js:74`). A pintura procedural e a prévia usam essa mesma conversão,
  por isso olhos, barriga e boca caem nas faces certas.
* **Orientação:** entidades olham para **-Z (norte)** (`forward_direction` padrão `-z`,
  `js/preview/preview.ts:96`); o lado **direito do animal fica em +X** (na exportação Bedrock o
  Blockbench inverte o X: `bone.pivot[0] *= -1`, `js/formats/bedrock/bedrock.js:1000`).
  Unidades em pixels (16 = 1 bloco), pés em Y = 0.
* **`visible_box`:** mesmo cálculo de `calculateVisibleBox`
  (`js/formats/bedrock/bedrock.js:640`); o valor gravado coincide com o que o Blockbench
  calcula (verificado no Blockbench).

## Projeto editável × formatos do Minecraft

| Arquivo | Para quê | Quem gera |
|---|---|---|
| `.bbmodel` | Projeto **editável** do Blockbench (cubos, ossos, pivôs, UV, textura embutida). O jogo não lê este arquivo. | Ninho Model Studio |
| `.png` | Textura (a mesma embutida no `.bbmodel`). Vai junto com a geometria no jogo. | Ninho Model Studio |
| `.geo.json` | Geometria **Bedrock** (e base do GeckoLib). | Blockbench: *File → Export → Export Bedrock Geometry* |
| Java/GeckoLib/animações | Etapa futura | — |

O exemplo `examples/trex-verde/blockbench/trex_verde.geo.json` foi exportado **pelo próprio
Blockbench 5.2.2** a partir do nosso `.bbmodel`, como prova de que a conversão funciona.
