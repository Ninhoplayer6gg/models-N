# Guia rápido: usar o Ninho Model Studio pelo celular (Android)

Tudo acontece no navegador, dentro do Google Colab. Não precisa de PC, terminal ou chave de API.

## 1. Abrir o notebook

* **Pelo link (mais fácil):** abra no Chrome
  `https://colab.research.google.com/github/Ninhoplayer6gg/models-N/blob/ccr-95e0f983-pm7raa/Ninho-Model-Studio.ipynb`
  (depois que a branch for mesclada, troque `ccr-95e0f983-pm7raa` por `main`).
  Entre com sua conta Google. Se aparecer aviso de que o notebook não é do Google, toque em
  **Executar mesmo assim** (ele é deste repositório).
* **Por arquivo:** baixe `Ninho-Model-Studio.ipynb` do GitHub e, no Colab, use
  **Arquivo → Fazer upload de notebook**.

Dica: com o celular deitado (paisagem) os formulários ficam mais confortáveis.

## 2. (Opcional) Ligar a GPU

Menu **Ambiente de execução → Alterar o tipo de ambiente de execução → T4 GPU → Salvar**.
Sem GPU tudo funciona, mas a IA fica lenta (1–3 min por descrição).

## 3. Executar as etapas, em ordem

Toque no ▶ à esquerda de cada etapa e espere o ✅.

1. **Preparar o ambiente** — alguns segundos.
2. **Carregar a IA** — na primeira vez baixa ~3 GB (alguns minutos). *Pule se for usar só o
   modo procedural.*
3. **Descrição e parâmetros** — escolha o modo, escreva a descrição e ajuste os controles
   (cabeça, cauda, pernas, cores, padrão, detalhe, textura 128/256, seed). Toque ▶.
4. **Gerar e visualizar** — mostra as vistas de frente, lado, topo, perspectiva, traseira e
   ventre, o atlas da textura, o esqueleto com os pivôs e um visualizador 3D
   (um dedo gira, dois dedos aproximam, dois toques voltam ao início).
5. **Baixar os arquivos** — baixa o `.zip`. Se o download não começar, toque no botão verde.

**Mudou algo?** Toque ▶ na Etapa 3 e depois ▶ na Etapa 4. Não precisa repetir as Etapas 1 e 2.
Com a mesma descrição e a mesma seed, a IA não é chamada de novo (o resultado anterior é
reaproveitado); marque *refazer_interpretacao* para pedir outra leitura.

## 4. Abrir no Blockbench pelo celular

1. No gerenciador de arquivos do Android, abra o `.zip` baixado e extraia (ou baixe
   *só o .bbmodel* na Etapa 5).
2. No Chrome, acesse `https://web.blockbench.net` → **File → Open Model** → escolha o
   `.bbmodel`. A textura já vem embutida.
3. Para o Minecraft Bedrock: **File → Export → Export Bedrock Geometry** (gera o `.geo.json`;
   use junto com o `.png`).

## 5. Se algo der errado

| Situação | O que fazer |
|---|---|
| "A IA não carregou" | Tente o modelo 0.5B ou *Ambiente de execução → Reiniciar sessão* e rode a Etapa 1 de novo. Enquanto isso, use o modo procedural. |
| "A IA não produziu um JSON válido" | A resposta da IA aparece na mensagem. Troque a seed, simplifique a descrição ou use o modo procedural. |
| A sessão caiu / os arquivos sumiram | O Colab gratuito encerra sessões paradas. Rode as etapas de novo; marque *copiar_para_o_google_drive* na Etapa 5 para guardar os arquivos. |
| Aviso "orçamento de elementos" | Aumente *orcamento_elementos* ou reduza o detalhe. |
| Aviso "escala reduzida" / "textura 256" | O modelo ficou grande demais para o atlas; o programa ajustou e avisou. |
