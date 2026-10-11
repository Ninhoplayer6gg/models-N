"""Funções usadas pelas células do notebook (mensagens em português).

Mantém as células do Colab curtas: cada etapa chama uma função daqui.
Funciona também fora do Colab (Jupyter local), sem os recursos de download.
"""

from __future__ import annotations

import base64
import html as _html
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from . import __version__
from .spec import (
    COLORS,
    BuildSettings,
    SpecValidationError,
    apply_adjustments,
    default_spec,
    normalize_hex,
)

OUT_DIR_DEFAULT = "/content/ninho_saida" if os.path.isdir("/content") else os.path.abspath("ninho_saida")

MODE_LABELS = {
    "IA (descrição livre)": "ia",
    "Procedural (parâmetros manuais)": "procedural",
}
PATTERN_PT = {"automático": None, "nenhum": "none", "listras": "stripes", "manchas": "spots", "faixas": "bands",
              "mosqueado": "mottled"}
SKIN_PT = {"automática": None, "escamas": "scales", "rugosa": "rough", "lisa": "smooth", "penas": "feathered"}
DETAIL_PT = {"automático": None, "baixo": "low", "médio": "medium", "alto": "high"}
JAW_PT = {"automática": None, "fechada": 0.0, "entreaberta": 0.35, "aberta": 0.65, "rugindo": 1.0}
INTENSITY_PT = {"automática": None, "suave": 0.35, "média": 0.6, "forte": 0.85}
TRI_PT = {"automático": None, "sim": True, "não": False}

# Nomes dos campos do formulário da Etapa 3 do notebook (na mesma ordem).
CAMPOS_FORMULARIO = (
    "modo", "descricao", "nome", "cabeca", "focinho", "pescoco", "tronco_comprimento", "tronco_volume", "bracos",
    "pernas_comprimento", "pernas_espessura", "cauda_comprimento", "cauda_espessura", "escala", "boca",
    "cor_principal", "cor_secundaria", "cor_barriga", "cor_padrao", "cor_olhos", "padrao", "intensidade_padrao",
    "pele", "detalhe", "chifres", "espinhos", "dentes", "cicatrizes", "crista_penas", "textura",
    "orcamento_elementos", "seed", "criatividade_ia", "tentativas_ia", "refazer_interpretacao",
)


@dataclass
class _State:
    llm: Any = None
    llm_error: Optional[str] = None
    ai_cache: dict[tuple, Any] = field(default_factory=dict)
    last_result: Any = None
    last_paths: dict[str, Any] = field(default_factory=dict)
    params: Optional[dict[str, Any]] = None


STATE = _State()


# ---------------------------------------------------------------------------
# exibição
# ---------------------------------------------------------------------------


def _in_notebook() -> bool:
    try:
        from IPython import get_ipython

        return get_ipython() is not None
    except ImportError:
        return False


def _has_colab() -> bool:
    try:
        import google.colab  # noqa: F401

        return True
    except ImportError:
        return False


def _show_html(markup: str) -> None:
    if _in_notebook():
        from IPython.display import HTML, display

        display(HTML(markup))
    else:
        import re

        print(re.sub(r"<[^>]+>", "", markup))


def _box(title: str, body: str, kind: str = "info") -> None:
    colors = {"info": ("#e8f1fb", "#1f5fa8"), "ok": ("#e7f6ea", "#1e7b34"), "warn": ("#fff6e0", "#946200"),
              "error": ("#fde8e8", "#a12020")}
    bg, fg = colors[kind]
    _show_html(
        f'<div style="background:{bg};border-left:6px solid {fg};padding:12px 14px;border-radius:10px;'
        f'margin:8px 0;font-size:15px;line-height:1.45;font-family:system-ui,sans-serif">'
        f'<b style="color:{fg}">{_html.escape(title)}</b><div style="margin-top:6px">{body}</div></div>'
    )


def _list(items: list[str]) -> str:
    if not items:
        return ""
    return "<ul style='margin:4px 0 0 18px;padding:0'>" + "".join(f"<li>{_html.escape(i)}</li>" for i in items) + "</ul>"


def _show_image(path: str, width: Optional[int] = None) -> None:
    if _in_notebook():
        from IPython.display import Image, display

        display(Image(filename=path, width=width))
    else:
        print(f"[imagem] {path}")


# ---------------------------------------------------------------------------
# Etapa 1 – ambiente
# ---------------------------------------------------------------------------


def preparar_ambiente() -> dict[str, Any]:
    info: dict[str, Any] = {"python": platform.python_version(), "ninho_model_studio": __version__}
    missing = []
    for mod in ("numpy", "PIL"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        _box("Faltam bibliotecas", f"Instale: {', '.join(missing)}", "error")
    try:
        import torch

        info["torch"] = torch.__version__
        info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except ImportError:
        info["torch"] = None
        info["gpu"] = None
    try:
        import transformers

        info["transformers"] = transformers.__version__
    except ImportError:
        info["transformers"] = None
    try:
        with open("/proc/meminfo") as fh:
            kb = int(fh.readline().split()[1])
        info["ram_gb"] = round(kb / 1024 / 1024, 1)
    except (OSError, ValueError, IndexError):
        info["ram_gb"] = None
    gpu = info["gpu"] or "nenhuma (a IA vai rodar na CPU, mais devagar)"
    body = (
        f"Ninho Model Studio {__version__} · Python {info['python']}<br>"
        f"GPU: <b>{_html.escape(str(gpu))}</b> · RAM: {info['ram_gb']} GB<br>"
        f"torch {info['torch']} · transformers {info['transformers']}"
    )
    _box("✅ Ambiente pronto", body, "ok")
    if info["torch"] is None or info["transformers"] is None:
        _box("Modo IA indisponível neste ambiente",
             "torch/transformers não foram encontrados. O modo procedural funciona normalmente.", "warn")
    return info


# ---------------------------------------------------------------------------
# Etapa 2 – IA
# ---------------------------------------------------------------------------


def carregar_ia(modelo: str, dispositivo: str = "automático") -> Any:
    from .ai import MODEL_CHOICES, LLMError, load_llm

    device = {"automático": "auto", "GPU": "cuda", "CPU": "cpu"}.get(dispositivo, dispositivo)
    if STATE.llm is not None:  # libera o modelo anterior antes de carregar outro (evita faltar memória)
        STATE.llm = None
        import gc

        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
    info = MODEL_CHOICES.get(modelo, {})
    if info:
        _box("Carregando a IA",
             f"{_html.escape(info['label'])} · licença {info['license']} · download ~{info['download_gb']} GB na "
             f"primeira vez.<br>{_html.escape(info['notes'])}", "info")
    t0 = time.perf_counter()
    try:
        llm = load_llm(modelo, device=device, progress=lambda m: print(m))
    except LLMError as exc:
        STATE.llm = None
        STATE.llm_error = str(exc)
        _box("❌ A IA não carregou",
             f"{_html.escape(str(exc))}<br><br>Você pode continuar no <b>modo procedural</b>: na Etapa 3 escolha "
             "“Procedural (parâmetros manuais)”.", "error")
        return None
    STATE.llm = llm
    STATE.llm_error = None
    d = llm.describe()
    _box("✅ IA carregada",
         f"{_html.escape(d['model_id'])} em <b>{d['device'].upper()}</b> ({d['dtype']}) em {time.perf_counter() - t0:.0f} s.",
         "ok")
    return llm


# ---------------------------------------------------------------------------
# Etapa 3 – parâmetros
# ---------------------------------------------------------------------------


def _color(value: str, label: str, problems: list[str]) -> Optional[str]:
    text = (value or "").strip().lower()
    if text in ("", "auto", "automático", "automatico", "automática"):
        return None
    try:
        return normalize_hex(text)
    except ValueError:
        problems.append(f"cor '{label}' inválida: {value!r} (use #rrggbb, ex.: #4f7a35, ou 'auto')")
        return None


def coletar_parametros(**f: Any) -> dict[str, Any]:
    """Converte os campos do formulário em parâmetros validados."""
    problems: list[str] = []
    mode = MODE_LABELS.get(f.get("modo"), f.get("modo"))
    if mode not in ("ia", "procedural"):
        problems.append(f"modo inválido: {f.get('modo')!r}")
    colors = {
        "primary": _color(f.get("cor_principal", "auto"), "principal", problems),
        "secondary": _color(f.get("cor_secundaria", "auto"), "secundária", problems),
        "belly": _color(f.get("cor_barriga", "auto"), "barriga", problems),
        "pattern": _color(f.get("cor_padrao", "auto"), "padrão", problems),
        "eyes": _color(f.get("cor_olhos", "auto"), "olhos", problems),
    }
    adjustments = {
        "proportions": {
            "head_size": f.get("cabeca", 1.0),
            "snout_length": f.get("focinho", 1.0),
            "neck_length": f.get("pescoco", 1.0),
            "body_length": f.get("tronco_comprimento", 1.0),
            "body_bulk": f.get("tronco_volume", 1.0),
            "arm_length": f.get("bracos", 1.0),
            "leg_length": f.get("pernas_comprimento", 1.0),
            "leg_thickness": f.get("pernas_espessura", 1.0),
            "tail_length": f.get("cauda_comprimento", 1.0),
            "tail_thickness": f.get("cauda_espessura", 1.0),
        },
        "scale": f.get("escala", 1.0),
        "jaw_open": JAW_PT.get(f.get("boca", "automática")),
        "colors": {k: v for k, v in colors.items() if v},
        "pattern_type": PATTERN_PT.get(f.get("padrao", "automático")),
        "pattern_intensity": INTENSITY_PT.get(f.get("intensidade_padrao", "automática")),
        "skin": SKIN_PT.get(f.get("pele", "automática")),
        "detail_level": DETAIL_PT.get(f.get("detalhe", "automático")),
        "features": {
            "brow_horns": TRI_PT.get(f.get("chifres", "automático")),
            "back_spikes": TRI_PT.get(f.get("espinhos", "automático")),
            "teeth_visible": TRI_PT.get(f.get("dentes", "automático")),
            "scars": TRI_PT.get(f.get("cicatrizes", "automático")),
            "feather_crest": TRI_PT.get(f.get("crista_penas", "automático")),
        },
        "name": (f.get("nome") or "").strip() or None,
    }
    try:
        texture = int(str(f.get("textura", "128")).split("x")[0])
    except ValueError:
        texture = 128
        problems.append("textura inválida (use 128 ou 256)")
    settings = BuildSettings(
        seed=int(f.get("seed", 42)),
        texture_size=texture,
        element_budget=int(f.get("orcamento_elementos", 64)),
    )
    problems += settings.validate()
    params = {
        "mode": mode,
        "description": (f.get("descricao") or "").strip(),
        "adjustments": adjustments,
        "settings": settings,
        "ai": {
            "temperature": float(f.get("criatividade_ia", 0.0)),
            "max_attempts": int(f.get("tentativas_ia", 3)),
            "force": bool(f.get("refazer_interpretacao", False)),
        },
    }
    STATE.params = params
    if problems:
        _box("⚠️ Revise os parâmetros", _list(problems), "warn")
        params["problems"] = problems
    else:
        label = "IA (descrição livre)" if mode == "ia" else "Procedural (parâmetros manuais)"
        _box("✅ Parâmetros salvos", f"Modo: <b>{label}</b> · seed {settings.seed} · textura {texture} · "
             f"orçamento {settings.element_budget} cubos.<br>Agora execute a <b>Etapa 4</b>.", "ok")
    return params


def _clean_adjustments(adj: dict[str, Any]) -> dict[str, Any]:
    out = {}
    props = {k: v for k, v in adj.get("proportions", {}).items() if v is not None and float(v) != 1.0}
    if props:
        out["proportions"] = props
    if adj.get("scale") not in (None, 1.0):
        out["scale"] = adj["scale"]
    for key in ("jaw_open", "pattern_type", "pattern_intensity", "skin", "detail_level", "name"):
        if adj.get(key) is not None:
            out[key] = adj[key]
    if adj.get("colors"):
        out["colors"] = adj["colors"]
    feats = {k: v for k, v in adj.get("features", {}).items() if v is not None}
    if feats:
        out["features"] = feats
    return out


# ---------------------------------------------------------------------------
# Etapa 4 – gerar e visualizar
# ---------------------------------------------------------------------------


def gerar_e_mostrar(params: Optional[dict[str, Any]] = None, llm: Any = None, out_dir: str = OUT_DIR_DEFAULT,
                    visualizador_3d: bool = True, mostrar_atlas: bool = True, mostrar_esqueleto: bool = True) -> Any:
    from .ai import interpret
    from .atlas import AtlasError
    from .builders import BudgetError
    from .export import save_outputs
    from .pipeline import generate

    params = params or STATE.params
    if not params:
        _box("Faltam os parâmetros", "Execute a Etapa 3 antes.", "error")
        return None
    if params.get("problems"):
        _box("❌ Parâmetros com problemas", _list(params["problems"]) + "Corrija na Etapa 3 e execute-a de novo.",
             "error")
        return None
    llm = llm if llm is not None else STATE.llm
    mode = params["mode"]
    description = params["description"]
    settings: BuildSettings = params["settings"]
    adjustments = _clean_adjustments(params["adjustments"])
    ai_info = None
    notes: list[str] = []

    if mode == "ia":
        if llm is None:
            reason = f" ({STATE.llm_error})" if STATE.llm_error else ""
            _box("❌ Modo IA sem modelo carregado",
                 f"A IA não está carregada{_html.escape(reason)}. Execute a <b>Etapa 2</b> ou mude o modo para "
                 "<b>Procedural (parâmetros manuais)</b> na Etapa 3. Nada foi gerado.", "error")
            return None
        if not description:
            _box("❌ Descrição vazia", "Escreva a descrição na Etapa 3 (modo IA).", "error")
            return None
        # com criatividade 0 a resposta não depende da seed: mudar só a seed não chama a IA de novo
        temperature = params["ai"]["temperature"]
        key = (llm.model_id, description, settings.seed if temperature > 0 else None, temperature,
               params["ai"]["max_attempts"])
        cached = STATE.ai_cache.get(key)
        if cached is not None and not params["ai"]["force"]:
            ai = cached
            _box("♻️ Usando a interpretação anterior da IA",
                 "Mesma descrição e mesmo modelo (com criatividade 0 a resposta seria igual). "
                 "Marque “refazer_interpretacao” para pedir outra.", "info")
        else:
            _box("🤖 Modo IA", f"Interpretando a descrição com <b>{_html.escape(llm.model_id)}</b>…", "info")
            ai = interpret(description, llm, seed=settings.seed, temperature=params["ai"]["temperature"],
                           max_attempts=params["ai"]["max_attempts"], progress=print)
            if ai.ok:
                STATE.ai_cache[key] = ai
        if not ai.ok:
            raw = ai.attempts[-1].get("raw_output") if ai.attempts else ""
            _box("❌ A IA não produziu um JSON válido",
                 _list(ai.errors) + f"<details><summary>Última resposta da IA</summary><pre style='white-space:pre-wrap'>"
                 f"{_html.escape(str(raw)[:3000])}</pre></details>"
                 "Opções: aumente “criatividade_ia” (ex.: 0.3, então a seed passa a variar a resposta), "
                 "simplifique a descrição, ou use o <b>modo procedural</b> "
                 "(Etapa 3 → “Procedural (parâmetros manuais)”).", "error")
            return None
        base = ai.spec
        ai_info = ai.info_for_config()
        _box("✅ IA interpretou a descrição",
             f"{len(ai.provided_fields)} campos vieram da IA ({len(ai.attempts)} tentativa(s), {ai.seconds:.1f} s)."
             + _list(ai.warnings), "ok")
    else:
        base = default_spec()
        if description:
            notes.append("modo procedural: a descrição foi guardada apenas como anotação (não foi interpretada)")

    try:
        spec, adj_notes = apply_adjustments(base, adjustments)
    except (SpecValidationError, ValueError) as exc:
        _box("❌ Ajuste inválido", _html.escape(str(exc)), "error")
        return None
    notes += adj_notes
    try:
        result = generate(spec, settings, mode=mode, description=description, ai_info=ai_info,
                          manual_adjustments=adjustments or None, extra_notes=notes)
    except BudgetError as exc:
        _box("❌ Orçamento de elementos pequeno demais", _html.escape(str(exc)) +
             f"<br>Aumente “orcamento_elementos” para pelo menos {exc.needed}.", "error")
        return None
    except AtlasError as exc:
        _box("❌ A textura não comporta este modelo", _html.escape(str(exc)), "error")
        return None
    except Exception as exc:  # noqa: BLE001
        _box("❌ Erro ao gerar o modelo", f"{type(exc).__name__}: {_html.escape(str(exc))}", "error")
        raise
    paths = save_outputs(result, out_dir)
    STATE.last_result = result
    STATE.last_paths = paths

    label = "IA + construtor procedural" if mode == "ia" else "procedural (sem IA)"
    v = result.validation
    summary = (
        f"<b>{_html.escape(result.spec['name'])}</b> · origem dos parâmetros: <b>{label}</b><br>"
        f"{result.model.cube_count} cubos · {len(result.model.bones)} ossos · textura {result.atlas.size}x{result.atlas.size} "
        f"(procedural) · {100 * result.atlas.usage:.0f}% da área do atlas reservada · seed {settings.seed}"
    )
    _box("✅ Modelo gerado" if v.ok else "⚠️ Modelo gerado com problemas", summary + _list(result.notes),
         "ok" if v.ok else "warn")
    _box("Validação do arquivo exportado", _html.escape(v.summary_pt()).replace("\n", "<br>"), "ok" if v.ok else "error")
    _show_image(paths["vistas"])
    if mostrar_atlas:
        _show_image(paths["atlas"], width=512)
    if mostrar_esqueleto:
        _show_image(paths["esqueleto"])
    if visualizador_3d:
        visualizar_3d(result)
    if ai_info:
        import json as _json

        _show_html("<details><summary><b>JSON validado vindo da IA</b></summary><pre style='white-space:pre-wrap'>"
                   + _html.escape(_json.dumps(ai_info["validated_ai_json"], ensure_ascii=False, indent=2))
                   + "</pre></details>")
    return result


def visualizar_3d(result: Any = None) -> None:
    from .mesh import build_mesh
    from .viewer import viewer_html, viewer_iframe

    result = result or STATE.last_result
    if result is None:
        _box("Nada para mostrar", "Gere um modelo na Etapa 4.", "warn")
        return
    page = viewer_html(build_mesh(result.bbmodel), result.png, title=result.spec.get("name", "modelo"),
                       element_id=f"nms-{int(time.time() * 1000)}")
    if _in_notebook():
        from IPython.display import HTML, display

        display(HTML(viewer_iframe(page)))
    else:
        print("visualizador disponível no arquivo _3d.html")


# ---------------------------------------------------------------------------
# Etapa 5 – downloads
# ---------------------------------------------------------------------------


def _data_link(path: str, label: str, mime: str) -> str:
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    name = os.path.basename(path)
    return (f'<a download="{_html.escape(name)}" href="data:{mime};base64,{b64}" '
            'style="display:inline-block;margin:6px 8px 6px 0;padding:12px 16px;background:#2f6b3a;color:#fff;'
            f'border-radius:10px;text-decoration:none;font-size:16px">⬇️ {_html.escape(label)}</a>')


def baixar_arquivos(o_que: str = "pacote .zip", copiar_para_drive: bool = False) -> None:
    paths = STATE.last_paths
    if not paths:
        _box("Nada para baixar", "Gere um modelo na Etapa 4 primeiro.", "warn")
        return
    choice = {
        "pacote .zip": ["zip"],
        "só o .bbmodel": ["bbmodel"],
        "só a textura .png": ["png"],
        "só o .json": ["json"],
        "só o .geo.json (Minecraft Java)": ["geo"],
        "todos separados": ["bbmodel", "png", "geo", "json", "zip"],
    }.get(o_que, ["zip"])
    mimes = {"zip": "application/zip", "bbmodel": "application/json", "png": "image/png", "json": "application/json",
             "geo": "application/json"}
    links = "".join(_data_link(paths[k], os.path.basename(paths[k]), mimes[k]) for k in choice)
    _box("Seus arquivos", "Se o download não começar sozinho, toque nos botões abaixo:<br>" + links, "ok")
    if _has_colab():
        from google.colab import files

        for k in choice:
            try:
                files.download(paths[k])
            except Exception as exc:  # noqa: BLE001
                print(f"files.download falhou para {paths[k]}: {exc} — use os botões acima.")
    else:
        print("Arquivos em:", os.path.dirname(paths["zip"]))
    if copiar_para_drive:
        salvar_no_drive()


def salvar_no_drive(pasta: str = "Ninho-Model-Studio") -> None:
    if not _has_colab():
        _box("Google Drive indisponível", "Esta opção só funciona no Google Colab.", "warn")
        return
    import shutil

    from google.colab import drive

    drive.mount("/content/drive")
    dest = os.path.join("/content/drive/MyDrive", pasta)
    os.makedirs(dest, exist_ok=True)
    for key in ("zip", "bbmodel", "png", "geo", "json"):
        if key in STATE.last_paths:
            shutil.copy2(STATE.last_paths[key], dest)
    _box("✅ Copiado para o Google Drive", f"Pasta: MyDrive/{_html.escape(pasta)}", "ok")


def cores_padrao() -> dict[str, str]:
    return {k: v[0] for k, v in COLORS.items()}
