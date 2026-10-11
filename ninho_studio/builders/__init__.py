"""Registro de construtores por plano corporal.

Para adicionar outra criatura (ex.: quadrúpede ou humanoide):

1. crie ``builders/<plano>.py`` com uma função ``build_with_budget(spec, settings)``
   que devolve ``(Model, notas)``;
2. registre-a em ``BUILDERS``;
3. acrescente a espécie em ``spec.SPECIES`` apontando para o plano.
"""

from __future__ import annotations

from typing import Any, Callable

from ..model import Model
from ..spec import SPECIES, BuildSettings
from .theropod import BudgetError, build_with_budget as _theropod

BUILDERS: dict[str, Callable[[dict[str, Any], BuildSettings], tuple[Model, list[str]]]] = {
    "theropod": _theropod,
}


def build_model(spec: dict[str, Any], settings: BuildSettings) -> tuple[Model, list[str]]:
    plan = SPECIES[spec["species"]]
    if plan not in BUILDERS:
        raise NotImplementedError(f"plano corporal ainda não implementado: {plan}")
    return BUILDERS[plan](spec, settings)


__all__ = ["BUILDERS", "BudgetError", "build_model"]
