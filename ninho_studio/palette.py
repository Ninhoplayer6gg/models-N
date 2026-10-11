"""Cores: conversões, rampas de sombreamento (pixel art) e nomes aproximados."""

from __future__ import annotations

import colorsys
from typing import Sequence

import numpy as np


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = (int(max(0, min(255, round(c)))) for c in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _hue_toward(h: float, target: float, amount: float) -> float:
    """Desloca o matiz ``h`` (0..1) em direção a ``target`` por ``amount`` (fração do círculo)."""
    diff = (target - h + 0.5) % 1.0 - 0.5
    step = max(-abs(amount), min(abs(amount), diff))
    return (h + step) % 1.0


def light_factor(rgb: Sequence[int]) -> float:
    """0 para cores comuns; até 1 para cores quase brancas (muito claras e pouco saturadas)."""
    _h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb[:3]))
    return max(0.0, min(1.0, (v - 0.75) / 0.25)) * max(0.0, min(1.0, (0.30 - s) / 0.30))


def shade(rgb: Sequence[int], level: int) -> tuple[int, int, int]:
    """Tom ``level`` de uma cor base com deslocamento de matiz típico de pixel art.

    Níveis negativos escurecem puxando para o azul/roxo; positivos clareiam
    puxando para o amarelo. Nível 0 devolve a própria cor. Cores quase brancas
    escurecem em passos menores e com sombra fria (azul-acinzentada), para um
    animal branco continuar parecendo branco e não cinza.
    """
    if level == 0:
        return tuple(int(c) for c in rgb[:3])  # type: ignore[return-value]
    r, g, b = (c / 255.0 for c in rgb[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if level < 0:
        k = -level
        step = 0.15 - 0.08 * light_factor(rgb)
        v = v * (1.0 - step * k)
        if s < 0.06:
            h, s = 0.60, min(0.22, s + 0.035 * k)  # branco/cinza: sombra fria
        else:
            s = min(1.0, s * (1.0 + 0.10 * k) + 0.02 * k)
            h = _hue_toward(h, 0.70, 0.022 * k)
    else:
        k = level
        v = min(1.0, v + (1.0 - v) * 0.22 * k + 0.05 * k)
        s = max(0.0, s * (1.0 - 0.10 * k))
        if s > 0.05:
            h = _hue_toward(h, 0.15, 0.018 * k)
    r, g, b = colorsys.hsv_to_rgb(h, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def detail_dark(rgb: Sequence[int]) -> tuple[int, int, int]:
    """Cor escura de detalhe (contorno do olho, narinas, dedos) com contraste garantido."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb[:3]))
    v = max(0.10, v * 0.42)
    if s < 0.06:
        h, s = 0.60, 0.12
    else:
        s = min(1.0, s * 1.1 + 0.05)
        h = _hue_toward(h, 0.70, 0.03)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def luminance(rgb: Sequence[int]) -> float:
    """Luminância relativa (0 a 1) no espaço sRGB linearizado."""
    def lin(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: Sequence[int], b: Sequence[int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class Ramp:
    """Rampa de tons discretos (-4..+3) de uma cor base."""

    LEVELS = range(-4, 4)

    def __init__(self, base_hex: str):
        self.base_hex = base_hex
        base = hex_to_rgb(base_hex)
        self.table = {lvl: shade(base, lvl) for lvl in self.LEVELS}

    def __getitem__(self, level: int) -> tuple[int, int, int]:
        level = max(min(self.LEVELS), min(max(self.LEVELS), int(level)))
        return self.table[level]

    def array(self) -> np.ndarray:
        """Matriz (8, 3) indexada por ``level + 4``."""
        return np.array([self.table[l] for l in self.LEVELS], dtype=np.uint8)


def mix(a: Sequence[int], b: Sequence[int], t: float) -> tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


_NAMES = [
    (0.000, "vermelho"),
    (0.040, "vermelho-alaranjado"),
    (0.075, "laranja"),
    (0.120, "amarelo-alaranjado"),
    (0.160, "amarelo"),
    (0.200, "verde-amarelado"),
    (0.270, "verde"),
    (0.420, "verde-azulado"),
    (0.500, "ciano"),
    (0.560, "azul-claro"),
    (0.640, "azul"),
    (0.730, "roxo"),
    (0.830, "magenta"),
    (0.920, "rosa"),
    (0.970, "vermelho"),
]


def color_name_pt(hex_value: str) -> str:
    """Nome aproximado em português (para mostrar ao usuário o que a IA escolheu)."""
    r, g, b = (c / 255.0 for c in hex_to_rgb(hex_value))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.16:
        return "preto"
    if s < 0.12:
        if v > 0.85:
            return "branco"
        if v > 0.55:
            return "cinza-claro"
        return "cinza" if v > 0.35 else "cinza-escuro"
    name = _NAMES[0][1]
    for start, label in _NAMES:
        if h >= start:
            name = label
    if name in ("laranja", "amarelo-alaranjado", "vermelho-alaranjado") and v < 0.6:
        name = "marrom"
    if name in ("amarelo",) and s < 0.45 and v > 0.7:
        name = "creme"
    prefix = ""
    if v < 0.4:
        prefix = " escuro"
    elif v > 0.85 and s < 0.5:
        prefix = " claro"
    return name + prefix
