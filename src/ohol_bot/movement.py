from __future__ import annotations

from collections import deque

from .game_data import OholObject
from .model import Tile, step_toward

_NEIGHBOR_OFFSETS = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


def tile_blocks_walking(
    tile: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
) -> bool:
    object_id = tile_objects.get(tile)
    if object_id is None:
        return False
    obj = objects.get(object_id)
    return bool(obj and obj.blocks_walking)


def can_step_to(
    from_tile: Tile,
    to_tile: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    blocked_tiles: set[Tile] | None = None,
) -> bool:
    if not is_walkable(
        to_tile, tile_objects, objects, blocked_tiles=blocked_tiles
    ):
        return False
    dx = to_tile.x - from_tile.x
    dy = to_tile.y - from_tile.y
    if abs(dx) == 1 and abs(dy) == 1:
        if not is_walkable(
            Tile(from_tile.x + dx, from_tile.y),
            tile_objects,
            objects,
            blocked_tiles=blocked_tiles,
        ):
            return False
        if not is_walkable(
            Tile(from_tile.x, from_tile.y + dy),
            tile_objects,
            objects,
            blocked_tiles=blocked_tiles,
        ):
            return False
    return True


def is_walkable(
    tile: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    blocked_tiles: set[Tile] | None = None,
) -> bool:
    if blocked_tiles and tile in blocked_tiles:
        return False
    return not tile_blocks_walking(tile, tile_objects, objects)


def _neighbors(tile: Tile) -> tuple[Tile, ...]:
    return tuple(Tile(tile.x + dx, tile.y + dy) for dx, dy in _NEIGHBOR_OFFSETS)


def resolve_approach_tile(
    target: Tile,
    start: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    blocked_tiles: set[Tile] | None = None,
) -> Tile | None:
    if is_walkable(
        target, tile_objects, objects, blocked_tiles=blocked_tiles
    ):
        return target
    candidates = [
        tile
        for tile in _neighbors(target)
        if is_walkable(tile, tile_objects, objects, blocked_tiles=blocked_tiles)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda tile: tile.distance_to(start))


def next_walkable_step(
    start: Tile,
    target: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    max_search: int = 48,
    blocked_tiles: set[Tile] | None = None,
) -> Tile | None:
    """Return the first step on a shortest path to target, avoiding blockers."""
    if start == target:
        return start
    effective_target = target
    if not is_walkable(
        target, tile_objects, objects, blocked_tiles=blocked_tiles
    ):
        resolved = resolve_approach_tile(
            target,
            start,
            tile_objects,
            objects,
            blocked_tiles=blocked_tiles,
        )
        if resolved is None:
            return None
        effective_target = resolved

    preferred = step_toward(start, effective_target)
    if (
        preferred != start
        and can_step_to(
            start,
            preferred,
            tile_objects,
            objects,
            blocked_tiles=blocked_tiles,
        )
    ):
        return preferred

    blocked = blocked_tiles or set()
    parent: dict[Tile, Tile | None] = {start: None}
    queue: deque[Tile] = deque([start])
    found = False
    while queue:
        current = queue.popleft()
        if current.distance_to(start) > max_search:
            continue
        if current == effective_target:
            found = True
            break
        for neighbor in _neighbors(current):
            if neighbor in parent:
                continue
            if not can_step_to(
                current,
                neighbor,
                tile_objects,
                objects,
                blocked_tiles=blocked,
            ):
                continue
            parent[neighbor] = current
            queue.append(neighbor)

    if not found:
        return None

    step = effective_target
    while parent[step] is not None and parent[step] != start:
        step = parent[step]
    if parent.get(step) != start:
        return None
    return step
