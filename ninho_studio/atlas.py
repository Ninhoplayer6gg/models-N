"""Distribui os cubos no atlas de textura (box UV) sem sobreposição."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Model
from .uv import PackItem, atlas_usage, box_uv_footprint, box_uv_shape, pack_best


class AtlasError(ValueError):
    pass


@dataclass
class AtlasInfo:
    size: int
    usage: float
    strategy: str
    upgraded: bool


def assign_uvs(model: Model, requested_size: int, auto_upgrade: bool = True) -> AtlasInfo:
    """Define ``uv_offset`` de cada cubo. Tenta 128 e, se permitido, 256."""
    cubes = list(model.iter_cubes())
    items = []
    for idx, cube in enumerate(cubes):
        w, h = box_uv_footprint(cube.size)
        items.append(PackItem(key=idx, width=w, height=h, group=int(cube.tags.get("region", 9)),
                              rects=box_uv_shape(cube.size)))
    sizes = [requested_size]
    if auto_upgrade and requested_size < 256:
        sizes.append(256)
    for size in sizes:
        placement, strategy = pack_best(items, size, size)
        if placement is None:
            continue
        for idx, cube in enumerate(cubes):
            cube.uv_offset = placement[idx]
        model.texture_width = size
        model.texture_height = size
        return AtlasInfo(size=size, usage=atlas_usage(items, size, size), strategy=strategy, upgraded=size != requested_size)
    need = sum(it.width * it.height for it in items)
    raise AtlasError(
        f"os {len(items)} cubos precisam de ~{need} pixels de atlas e não couberam em {sizes[-1]}x{sizes[-1]}; "
        "reduza a escala, o nível de detalhe ou o orçamento de elementos"
    )
