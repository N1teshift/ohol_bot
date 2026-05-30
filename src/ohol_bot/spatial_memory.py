from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .model import Tile
from .resource_memory import is_priority_landmark, matches_collect_landmark

if TYPE_CHECKING:
    from .game_data import OholGameData

WORKING_RADIUS = 24
LONG_TERM_MAX_ENTRIES = 500
LONG_TERM_STALE_TICKS = 3000


@dataclass(frozen=True, slots=True)
class TileMemory:
    """Object belief at an absolute world tile."""

    tile: Tile
    object_id: int
    name: str
    food_value: int
    last_seen_tick: int
    biome_id: int | None = None


@dataclass(frozen=True, slots=True)
class SpatialMemorySyncStats:
    working_count: int
    long_term_count: int
    promoted_this_tick: int
    forgotten_this_tick: int


@dataclass
class SpatialMemory:
    working: dict[Tile, TileMemory] = field(default_factory=dict)
    long_term: dict[Tile, TileMemory] = field(default_factory=dict)

    def forget_tile(self, abs_tile: Tile) -> bool:
        removed = abs_tile in self.working or abs_tile in self.long_term
        self.working.pop(abs_tile, None)
        self.long_term.pop(abs_tile, None)
        return removed

    def on_map_update(
        self,
        abs_tile: Tile,
        object_id: int,
        *,
        game_data: OholGameData | None,
        tick: int,
        center_abs: Tile | None,
        tile_biomes: dict[Tile, int] | None = None,
        radius: int = WORKING_RADIUS,
    ) -> None:
        if object_id <= 0:
            self.forget_tile(abs_tile)
            return
        if center_abs is None:
            return
        if abs_tile.distance_to(center_abs) > radius:
            return
        biome_id = tile_biomes.get(abs_tile) if tile_biomes is not None else None
        entry = entry_from_tile(
            abs_tile, object_id, game_data, tick, biome_id=biome_id
        )
        self.working[abs_tile] = entry
        self.long_term.pop(abs_tile, None)

    def sync(
        self,
        center_abs: Tile,
        tile_objects: dict[Tile, int],
        game_data: OholGameData | None,
        tick: int,
        *,
        tile_biomes: dict[Tile, int] | None = None,
        radius: int = WORKING_RADIUS,
    ) -> SpatialMemorySyncStats:
        previous_working = self.working
        new_working: dict[Tile, TileMemory] = {}
        for abs_tile, object_id in tile_objects.items():
            if object_id <= 0:
                continue
            if center_abs.distance_to(abs_tile) > radius:
                continue
            biome_id = tile_biomes.get(abs_tile) if tile_biomes is not None else None
            new_working[abs_tile] = entry_from_tile(
                abs_tile,
                object_id,
                game_data,
                tick,
                biome_id=biome_id,
            )

        promoted = 0
        for abs_tile, entry in previous_working.items():
            if abs_tile not in new_working:
                promoted_entry = TileMemory(
                    tile=entry.tile,
                    object_id=entry.object_id,
                    name=entry.name,
                    food_value=entry.food_value,
                    last_seen_tick=tick,
                    biome_id=entry.biome_id,
                )
                self.long_term[abs_tile] = promoted_entry
                promoted += 1

        for abs_tile in new_working:
            self.long_term.pop(abs_tile, None)

        self.working = new_working

        forgotten = self._evict_stale(tick)
        forgotten += self._enforce_cap()

        return SpatialMemorySyncStats(
            working_count=len(self.working),
            long_term_count=len(self.long_term),
            promoted_this_tick=promoted,
            forgotten_this_tick=forgotten,
        )

    def _evict_stale(self, tick: int) -> int:
        stale = [
            tile
            for tile, entry in self.long_term.items()
            if tick - entry.last_seen_tick > LONG_TERM_STALE_TICKS
        ]
        for tile in stale:
            del self.long_term[tile]
        return len(stale)

    def _enforce_cap(self) -> int:
        forgotten = 0
        while len(self.long_term) > LONG_TERM_MAX_ENTRIES:
            oldest_tile = min(
                self.long_term,
                key=lambda tile: (
                    0
                    if is_priority_landmark(
                        self.long_term[tile].name,
                        self.long_term[tile].food_value,
                    )
                    else 1,
                    self.long_term[tile].last_seen_tick,
                ),
            )
            del self.long_term[oldest_tile]
            forgotten += 1
        return forgotten

    def long_term_food_count(self) -> int:
        return sum(1 for entry in self.long_term.values() if entry.food_value > 0)

    def nearest_food(
        self,
        store: dict[Tile, TileMemory],
        center_abs: Tile,
        *,
        exclude: frozenset[Tile] | None = None,
    ) -> TileMemory | None:
        return self.nearest_named(
            store,
            center_abs,
            names=set(),
            food_only=True,
            exclude_abs=exclude,
        )

    def nearest_named(
        self,
        store: dict[Tile, TileMemory],
        center_abs: Tile,
        names: set[str],
        *,
        food_only: bool = False,
        collect_landmarks: bool = False,
        biome_id: int | None = None,
        exclude_abs: frozenset[Tile] | None = None,
    ) -> TileMemory | None:
        blocked = exclude_abs or frozenset()
        candidates: list[TileMemory] = []
        for entry in store.values():
            if entry.tile in blocked:
                continue
            if biome_id is not None and entry.biome_id != biome_id:
                continue
            if food_only:
                if entry.food_value <= 0:
                    continue
            elif collect_landmarks:
                if not matches_collect_landmark(entry.name):
                    continue
            elif entry.name not in names:
                continue
            candidates.append(entry)
        if not candidates:
            return None
        return min(candidates, key=lambda entry: center_abs.distance_to(entry.tile))

    def long_term_food_preview(
        self,
        center_abs: Tile,
        *,
        limit: int = 3,
    ) -> tuple[dict[str, object], ...]:
        return self._long_term_preview(
            center_abs,
            predicate=lambda entry: entry.food_value > 0,
            limit=limit,
        )

    def long_term_collect_preview(
        self,
        center_abs: Tile,
        *,
        limit: int = 3,
    ) -> tuple[dict[str, object], ...]:
        return self._long_term_preview(
            center_abs,
            predicate=lambda entry: matches_collect_landmark(entry.name),
            limit=limit,
        )

    def _long_term_preview(
        self,
        center_abs: Tile,
        *,
        predicate: Callable[[TileMemory], bool],
        limit: int,
    ) -> tuple[dict[str, object], ...]:
        entries = [entry for entry in self.long_term.values() if predicate(entry)]
        entries.sort(key=lambda entry: center_abs.distance_to(entry.tile))
        preview: list[dict[str, object]] = []
        for entry in entries[:limit]:
            preview.append(
                {
                    "x": entry.tile.x,
                    "y": entry.tile.y,
                    "name": entry.name,
                    "last_seen_tick": entry.last_seen_tick,
                    "distance": center_abs.distance_to(entry.tile),
                    "biome_id": entry.biome_id,
                }
            )
        return tuple(preview)

    def long_term_by_biome_counts(
        self,
        game_data: OholGameData | None,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.long_term.values():
            if entry.biome_id is None:
                label = "unknown"
            elif game_data is not None:
                label = game_data.biome_name(entry.biome_id)
            else:
                label = f"Biome {entry.biome_id}"
            counts[label] = counts.get(label, 0) + 1
        return counts


def remembered_target_fact(
    entry: TileMemory,
    center_abs: Tile,
    to_relative: Callable[[Tile], Tile],
) -> dict[str, object]:
    rel = to_relative(entry.tile)
    biome_id = entry.biome_id
    return {
        "name": entry.name,
        "rel_x": rel.x,
        "rel_y": rel.y,
        "abs_x": entry.tile.x,
        "abs_y": entry.tile.y,
        "biome_id": biome_id,
        "food_value": entry.food_value,
        "distance": center_abs.distance_to(entry.tile),
        "last_seen_tick": entry.last_seen_tick,
    }


def entry_from_tile(
    abs_tile: Tile,
    object_id: int,
    game_data: OholGameData | None,
    tick: int,
    *,
    biome_id: int | None = None,
) -> TileMemory:
    if game_data is not None:
        obj = game_data.objects.get(object_id)
        name = obj.name if obj else f"unknown:{object_id}"
        food_value = obj.food_value if obj else 0
    else:
        name = f"object:{object_id}"
        food_value = 0
    return TileMemory(
        tile=abs_tile,
        object_id=object_id,
        name=name,
        food_value=food_value,
        last_seen_tick=tick,
        biome_id=biome_id,
    )
