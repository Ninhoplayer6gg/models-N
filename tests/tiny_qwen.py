"""Cria um modelo Qwen2 minúsculo com pesos aleatórios (só para testar o código do modo IA).

Não substitui o modelo real: as respostas são aleatórias. Serve para exercitar
o mesmo caminho do transformers usado no Colab (AutoTokenizer/AutoModel,
chat template, generate, critério de parada e decodificação).
"""

from __future__ import annotations

import os

CHATML_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"
)


def make_tiny_qwen(path: str) -> str:
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from transformers import PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM

    os.makedirs(path, exist_ok=True)
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    specials = ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]
    trainer = trainers.BpeTrainer(vocab_size=400, special_tokens=specials,
                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet())
    corpus = ['{"species": "t_rex", "name": "T-rex verde", "scale": 1.0, "colors": {"primary": "#4f7a35"}}',
              "Descrição: um T-rex verde com listras", "system user assistant"] * 50
    tok.train_from_iterator(corpus, trainer)
    fast = PreTrainedTokenizerFast(tokenizer_object=tok, eos_token="<|im_end|>", pad_token="<|endoftext|>",
                                   additional_special_tokens=["<|im_start|>"])
    fast.chat_template = CHATML_TEMPLATE
    fast.save_pretrained(path)
    cfg = Qwen2Config(vocab_size=len(fast), hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=8192,
                      tie_word_embeddings=True, eos_token_id=fast.eos_token_id, pad_token_id=fast.pad_token_id)
    model = Qwen2ForCausalLM(cfg)
    model.save_pretrained(path)
    return path
