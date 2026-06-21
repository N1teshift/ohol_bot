from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .model import ObjectState, Tile
from .tiles import chebyshev

if TYPE_CHECKING:
    from .game_data import OholGameData

# Fallback when game data is unavailable (names include OHOL variant suffixes).
DANGEROUS_NAME_PHRASES = (
    "mosquito swarm",
    "wild boar",
    "grizzly bear",
    "hungry grizzly bear",
    "rattle snake",
)
DANGEROUS_EXACT_BASE_NAMES = frozenset(
    {
        "wolf",
        "@ deadly wolf",
    }
)


def base_object_name(name: str) -> str:
    return name.split("#", 1)[0].strip().lower()


def is_dangerous_name(name: str) -> bool:
    base = base_object_name(name)
    if base in DANGEROUS_EXACT_BASE_NAMES:
        return True
    return any(phrase in base for phrase in DANGEROUS_NAME_PHRASES)


def is_dangerous_object(
    obj: ObjectState,
    game_data: OholGameData | None = None,
) -> bool:
    if game_data is not None:
        entry = game_data.objects.get(obj.object_id)
        if entry is not None:
            return entry.deadly_distance > 0 or is_dangerous_name(obj.name)
    return is_dangerous_name(obj.name)


def dangerous_tiles(
    nearby_objects: Iterable[ObjectState],
    game_data: OholGameData | None = None,
) -> frozenset[Tile]:
    return frozenset(
        obj.tile
        for obj in nearby_objects
        if is_dangerous_object(obj, game_data)
    )


def dangerous_objects_preview(
    nearby_objects: Iterable[ObjectState],
    game_data: OholGameData | None = None,
    *,
    limit: int = 8,
) -> tuple[dict[str, object], ...]:
    entries = [
        {"x": obj.tile.x, "y": obj.tile.y, "name": obj.name}
        for obj in nearby_objects
        if is_dangerous_object(obj, game_data)
    ]
    entries.sort(key=lambda item: (int(item["x"]), int(item["y"])))
    return tuple(entries[:limit])


def danger_path_blockers(
    danger_tiles: Iterable[Tile],
    *,
    buffer: int = 1,
) -> frozenset[Tile]:
    """Tiles pathfinding must not enter: danger tile plus a Chebyshev buffer."""
    blocked: set[Tile] = set()
    radius = max(0, buffer)
    for tile in danger_tiles:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) <= radius:
                    blocked.add(Tile(tile.x + dx, tile.y + dy))
    return frozenset(blocked)


def danger_near_route(
    start: Tile,
    target: Tile,
    danger_tiles: Iterable[Tile],
    *,
    start_radius: int = 3,
    target_radius: int = 2,
    corridor: int = 2,
) -> bool:
    """True when a danger tile sits near the current move corridor."""
    min_x = min(start.x, target.x) - corridor
    max_x = max(start.x, target.x) + corridor
    min_y = min(start.y, target.y) - corridor
    max_y = max(start.y, target.y) + corridor
    for tile in danger_tiles:
        if chebyshev(tile, start) <= start_radius:
            return True
        if chebyshev(tile, target) <= target_radius:
            return True
        if min_x <= tile.x <= max_x and min_y <= tile.y <= max_y:
            return True
    return False

