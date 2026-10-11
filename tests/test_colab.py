import json
import os

from ninho_studio import colab

FORM = dict(
    modo="Procedural (parâmetros manuais)", descricao="T-rex verde", nome="", cabeca=1.2, focinho=1.0, pescoco=1.0,
    tronco_comprimento=1.0, tronco_volume=1.0, bracos=1.0, pernas_comprimento=1.0, pernas_espessura=1.0,
    cauda_comprimento=1.0, cauda_espessura=1.0, escala=1.0, boca="automática", cor_principal="auto",
    cor_secundaria="auto", cor_barriga="auto", cor_padrao="auto", cor_olhos="auto", padrao="automático",
    intensidade_padrao="automática", pele="automática", detalhe="automático", chifres="automático",
    espinhos="automático", dentes="automático", cicatrizes="automático", crista_penas="automático", textura="128",
    orcamento_elementos=64, seed=42, criatividade_ia=0.0, tentativas_ia=3, refazer_interpretacao=False,
)


def test_collect_parameters_maps_labels():
    p = colab.coletar_parametros(**{**FORM, "padrao": "manchas", "boca": "rugindo", "cor_principal": "#123456",
                                    "chifres": "sim", "detalhe": "alto"})
    assert p["mode"] == "procedural"
    adj = p["adjustments"]
    assert adj["pattern_type"] == "spots" and adj["jaw_open"] == 1.0
    assert adj["colors"] == {"primary": "#123456"}
    assert adj["features"]["brow_horns"] is True and adj["features"]["scars"] is None
    assert adj["detail_level"] == "high"
    assert "problems" not in p


def test_collect_parameters_reports_problems():
    p = colab.coletar_parametros(**{**FORM, "cor_principal": "verdinho", "textura": "64"})
    assert p["problems"]


def test_generate_procedural(tmp_path):
    p = colab.coletar_parametros(**FORM)
    res = colab.gerar_e_mostrar(p, out_dir=str(tmp_path), visualizador_3d=False)
    assert res is not None and res.validation.ok
    assert res.config["mode"] == "procedural"
    assert res.spec["proportions"]["head_size"] == 1.2
    assert os.path.exists(colab.STATE.last_paths["zip"])
    assert any("anotação" in n for n in res.notes)


def test_ai_mode_without_model_does_not_generate(tmp_path):
    colab.STATE.llm = None
    colab.STATE.last_result = None
    p = colab.coletar_parametros(**{**FORM, "modo": "IA (descrição livre)"})
    res = colab.gerar_e_mostrar(p, out_dir=str(tmp_path), visualizador_3d=False)
    assert res is None  # nunca troca para o procedural em silêncio
    assert colab.STATE.last_result is None


def test_ai_mode_with_fake_llm(tmp_path, fake_llm_factory):
    reply = json.dumps({"species": "t_rex", "name": "Rex roxo", "colors": {"primary": "#6a2c8c"},
                        "proportions": {"head_size": 1.3}})
    llm = fake_llm_factory([reply])
    p = colab.coletar_parametros(**{**FORM, "modo": "IA (descrição livre)", "descricao": "um T-rex roxo cabeçudo",
                                    "cabeca": 1.0, "seed": 7})
    res = colab.gerar_e_mostrar(p, llm=llm, out_dir=str(tmp_path), visualizador_3d=False)
    assert res is not None and res.config["mode"] == "ia"
    assert res.spec["colors"]["primary"] == "#6a2c8c"
    assert res.spec["proportions"]["head_size"] == 1.3
    assert res.config["ai"]["validated_ai_json"]["name"] == "Rex roxo"
    # segunda execução com a mesma descrição usa o cache (não chama o modelo de novo)
    res2 = colab.gerar_e_mostrar(p, llm=llm, out_dir=str(tmp_path), visualizador_3d=False)
    assert res2 is not None and len(llm.calls) == 1


def test_ai_failure_reports_and_stops(tmp_path, fake_llm_factory):
    llm = fake_llm_factory(["nada", "nada", "nada"])
    p = colab.coletar_parametros(**{**FORM, "modo": "IA (descrição livre)", "descricao": "outro pedido", "seed": 99})
    assert colab.gerar_e_mostrar(p, llm=llm, out_dir=str(tmp_path), visualizador_3d=False) is None


def test_downloads_without_colab(tmp_path, capsys):
    p = colab.coletar_parametros(**FORM)
    colab.gerar_e_mostrar(p, out_dir=str(tmp_path), visualizador_3d=False)
    colab.baixar_arquivos("todos separados")
    out = capsys.readouterr().out
    assert "Arquivos em" in out


def test_ai_cache_ignores_seed_when_deterministic(tmp_path, fake_llm_factory):
    reply = json.dumps({"species": "t_rex", "name": "Rex"})
    llm = fake_llm_factory([reply, reply])
    base = {**FORM, "modo": "IA (descrição livre)", "descricao": "rex com seed variando"}
    colab.gerar_e_mostrar(colab.coletar_parametros(**{**base, "seed": 1}), llm=llm, out_dir=str(tmp_path),
                          visualizador_3d=False)
    res = colab.gerar_e_mostrar(colab.coletar_parametros(**{**base, "seed": 2}), llm=llm, out_dir=str(tmp_path),
                                visualizador_3d=False)
    assert res is not None and len(llm.calls) == 1  # mesma interpretação, nova seed só para forma/textura
    assert res.config["seed"] == 2
