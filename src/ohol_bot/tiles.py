from __future__ import annotations

from typing import Any, Mapping

from .model import Observation, Tile


def chebyshev(a: Tile, b: Tile) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def is_adjacent(a: Tile, b: Tile) -> bool:
    return chebyshev(a, b) == 1


def is_adjacent_or_same(a: Tile, b: Tile) -> bool:
    return chebyshev(a, b) <= 1


def is_orthogonally_adjacent(a: Tile, b: Tile) -> bool:
    return abs(a.x - b.x) + abs(a.y - b.y) == 1


def tile_from_fact(raw: Any) -> Tile | None:
    if isinstance(raw, Tile):
        return raw
    if isinstance(raw, Mapping):
        x = raw.get("x")
        y = raw.get("y")
        if x is None or y is None:
            return None
        try:
            return Tile(int(x), int(y))
        except (TypeError, ValueError):
            return None
    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        try:
            return Tile(int(raw[0]), int(raw[1]))
        except (TypeError, ValueError):
            return None
    return None


def tile_sequence_from_facts(raw: Any) -> tuple[Tile, ...]:
    if not isinstance(raw, (tuple, list)):
        return ()
    tiles: list[Tile] = []
    for item in raw:
        tile = tile_from_fact(item)
        if tile is not None:
            tiles.append(tile)
    return tuple(tiles)


def tile_set_from_facts(raw: Any) -> set[Tile]:
    return set(tile_sequence_from_facts(raw))


def tile_frozenset_from_facts(raw: Any) -> frozenset[Tile]:
    return frozenset(tile_sequence_from_facts(raw))


def tile_dict_from_facts(raw: Any) -> Tile | None:
    return tile_from_fact(raw)


def danger_tiles(observation: Observation) -> set[Tile]:
    facts = observation.facts
    tiles = tile_set_from_facts(facts.get("avoid_targets"))
    tiles.update(tile_set_from_facts(facts.get("danger_tiles")))
    return tiles
