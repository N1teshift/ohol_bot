from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model import Observation, Tile


@dataclass(frozen=True, slots=True)
class RememberedTarget:
    name: str
    tile: Tile
    distance: int | None = None


@dataclass(frozen=True, slots=True)
class PlannerFacts:
    avoid_targets: frozenset[Tile]
    blocked_tiles: frozenset[Tile]
    previous_tile: Tile | None
    nearest_remembered_food: RememberedTarget | None
    nearest_remembered_collect: RememberedTarget | None


def planner_facts(observation: Observation) -> PlannerFacts:
    facts = observation.facts
    return PlannerFacts(
        avoid_targets=_tile_tuple_set(facts.get("avoid_targets")),
        blocked_tiles=_tile_tuple_set(facts.get("blocked_tiles")),
        previous_tile=_tile_dict(facts.get("previous_tile")),
        nearest_remembered_food=_remembered_target(
            facts.get("nearest_remembered_food")
        ),
        nearest_remembered_collect=_remembered_target(
            facts.get("nearest_remembered_collect")
        ),
    )


def _tile_tuple_set(raw: Any) -> frozenset[Tile]:
    if not isinstance(raw, tuple):
        return frozenset()
    return frozenset(Tile(int(x), int(y)) for x, y in raw)


def _tile_dict(raw: Any) -> Tile | None:
    if not isinstance(raw, Mapping):
        return None
    x = raw.get("x")
    y = raw.get("y")
    if x is None or y is None:
        return None
    return Tile(int(x), int(y))


def _remembered_target(raw: Any) -> RememberedTarget | None:
    if not isinstance(raw, Mapping):
        return None
    rel_x = raw.get("rel_x")
    rel_y = raw.get("rel_y")
    if rel_x is None or rel_y is None:
        return None
    distance_raw = raw.get("distance")
    distance = int(distance_raw) if isinstance(distance_raw, (int, float)) else None
    return RememberedTarget(
        name=str(raw.get("name", "resource")),
        tile=Tile(int(rel_x), int(rel_y)),
        distance=distance,
    )
