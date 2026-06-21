from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model import Observation, Tile
from .tiles import tile_dict_from_facts, tile_frozenset_from_facts


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
        avoid_targets=tile_frozenset_from_facts(facts.get("avoid_targets")),
        blocked_tiles=tile_frozenset_from_facts(facts.get("blocked_tiles")),
        previous_tile=tile_dict_from_facts(facts.get("previous_tile")),
        nearest_remembered_food=_remembered_target(
            facts.get("nearest_remembered_food")
        ),
        nearest_remembered_collect=_remembered_target(
            facts.get("nearest_remembered_collect")
        ),
    )


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
