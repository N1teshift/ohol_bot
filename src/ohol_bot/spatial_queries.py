from __future__ import annotations

from collections.abc import Callable

from .model import ObjectState, Observation, Tile
from .object_names import normalize_item_name
from .tiles import danger_tiles


def object_at_tile(observation: Observation, tile: Tile) -> ObjectState | None:
    for obj in observation.nearby_objects:
        if obj.tile == tile:
            return obj
    return None


def nearest_object(
    observation: Observation,
    *,
    names: frozenset[str] | set[str] | None = None,
    object_ids: frozenset[int] | set[int] | None = None,
    predicate: Callable[[ObjectState], bool] | None = None,
    exclude_tiles: set[Tile] | frozenset[Tile] | None = None,
    skip_danger: bool = True,
    skip_depot: Tile | None = None,
    normalize_names: bool = True,
) -> ObjectState | None:
    excluded = set(exclude_tiles or ())
    if skip_danger:
        excluded.update(danger_tiles(observation))

    normalized_names: frozenset[str] | None = None
    if names is not None:
        if normalize_names:
            normalized_names = frozenset(normalize_item_name(name) for name in names)
        else:
            normalized_names = frozenset(names)

    id_set = frozenset(object_ids) if object_ids is not None else None
    candidates: list[ObjectState] = []
    for obj in observation.nearby_objects:
        if skip_depot is not None and obj.tile == skip_depot:
            continue
        if obj.tile in excluded:
            continue
        if normalized_names is not None:
            obj_name = (
                normalize_item_name(obj.name) if normalize_names else obj.name
            )
            if obj_name not in normalized_names:
                continue
        if id_set is not None and obj.object_id not in id_set:
            continue
        if predicate is not None and not predicate(obj):
            continue
        candidates.append(obj)

    if not candidates:
        return None
    return min(candidates, key=lambda obj: observation.self.tile.distance_to(obj.tile))
