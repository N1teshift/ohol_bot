from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True, slots=True)
class Tile:
    x: int
    y: int

    def distance_to(self, other: "Tile") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def chebyshev_to(self, other: "Tile") -> int:
        from .tiles import chebyshev

        return chebyshev(self, other)

    def is_adjacent_to(self, other: "Tile") -> bool:
        from .tiles import is_adjacent

        return is_adjacent(self, other)


def step_toward(start: Tile, target: Tile) -> Tile:
    if start == target:
        return start
    dx = target.x - start.x
    dy = target.y - start.y
    if abs(dx) >= abs(dy) and dx != 0:
        return Tile(start.x + (1 if dx > 0 else -1), start.y)
    if dy != 0:
        return Tile(start.x, start.y + (1 if dy > 0 else -1))
    return start


class ActionType(str, Enum):
    MOVE_TO = "move_to"
    PICK_UP = "pick_up"
    USE = "use"
    USE_SELF = "use_self"
    DROP = "drop"
    SAY = "say"
    FORCE = "force"
    WAIT = "wait"


@dataclass(frozen=True, slots=True)
class Action:
    type: ActionType
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObjectState:
    object_id: int
    name: str
    tile: Tile
    food_value: int = 0
    portable: bool = True
    biome_id: int | None = None
    floor_id: int | None = None


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: int
    tile: Tile
    age: float
    food_store: int
    max_food_store: int
    held_object_id: int | None = None
    held_food_value: int = 0
    held_object_name: str | None = None
    held_baby_id: int | None = None
    held_by_player_id: int | None = None
    held_yum: bool = False
    held_pending: bool = False
    yum_bonus: int = 0
    yum_multiplier: int = 0
    craving_food_id: int | None = None
    craving_yum_bonus: int = 0
    is_stationary: bool = True
    mother_id: int | None = None
    lineage_id: int | None = None
    ancestor_ids: tuple[int, ...] = ()
    relation_to_self: str | None = None
    display_id: int | None = None
    first_name: str | None = None
    family_name: str | None = None
    race_id: int = 0
    race_name: str | None = None

    @property
    def display_name(self) -> str | None:
        if self.first_name and self.family_name:
            return f"{self.first_name} {self.family_name}"
        if self.first_name:
            return self.first_name
        if self.family_name:
            return self.family_name
        return None

    @property
    def hunger_ratio(self) -> float:
        if self.max_food_store <= 0:
            return 0.0
        return self.food_store / self.max_food_store

    @property
    def missing_food_pips(self) -> int:
        if self.max_food_store <= 0:
            return 0
        return max(0, self.max_food_store - self.food_store)

    @property
    def is_hungry(self) -> bool:
        """True when base stomach pips missing meet planner threshold."""
        from .hunger import is_planner_hungry

        return is_planner_hungry(self)

    @property
    def effective_food_points(self) -> int:
        """Base food store plus stored yum bonus pips (game UI total)."""
        return self.food_store + self.yum_bonus

    @property
    def is_being_carried(self) -> bool:
        return self.held_by_player_id is not None and self.held_by_player_id > 0

    @property
    def is_holding_food(self) -> bool:
        return self.held_food_value > 0 or self.held_yum


@dataclass(frozen=True, slots=True)
class Observation:
    tick: int
    self: PlayerState
    nearby_objects: tuple[ObjectState, ...] = ()
    nearby_players: tuple[PlayerState, ...] = ()
    home: Tile | None = None
    home_radius: int | None = None
    self_biome_id: int | None = None
    self_floor_id: int | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    def nearest_food(self, exclude: frozenset[Tile] | None = None) -> ObjectState | None:
        blocked = exclude or frozenset()
        foods = [
            obj
            for obj in self.nearby_objects
            if obj.food_value > 0 and obj.tile not in blocked
        ]
        if not foods:
            return None
        return min(foods, key=lambda obj: self.self.tile.distance_to(obj.tile))

    def objects_named(self, *names: str) -> tuple[ObjectState, ...]:
        wanted = set(names)
        return tuple(obj for obj in self.nearby_objects if obj.name in wanted)

    def nearest_object(
        self,
        *,
        names: frozenset[str] | set[str] | None = None,
        object_ids: frozenset[int] | set[int] | None = None,
        predicate: Callable[[ObjectState], bool] | None = None,
        exclude_tiles: set[Tile] | frozenset[Tile] | None = None,
        skip_danger: bool = True,
        skip_depot: Tile | None = None,
        normalize_names: bool = True,
    ) -> ObjectState | None:
        from .spatial_queries import nearest_object

        return nearest_object(
            self,
            names=names,
            object_ids=object_ids,
            predicate=predicate,
            exclude_tiles=exclude_tiles,
            skip_danger=skip_danger,
            skip_depot=skip_depot,
            normalize_names=normalize_names,
        )

    def nearby_biome_counts(self) -> dict[int, int]:
        raw = self.facts.get("nearby_biome_counts")
        if isinstance(raw, dict):
            return {int(key): int(value) for key, value in raw.items()}
        return {}
