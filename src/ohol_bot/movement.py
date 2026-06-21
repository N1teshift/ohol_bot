from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .game_data import OholObject
from .model import Tile

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


@dataclass(frozen=True, slots=True)
class PathDiagnostics:
    start: Tile
    target: Tile
    effective_target: Tile | None
    path: tuple[Tile, ...]
    ok: bool
    reason: str
    method: str
    visited_tiles: int = 0
    max_search: int = 48
    max_steps: int = 6

    def as_fact(self) -> dict[str, object]:
        return {
            "start": _tile_fact(self.start),
            "target": _tile_fact(self.target),
            "effective_target": (
                _tile_fact(self.effective_target)
                if self.effective_target is not None
                else None
            ),
            "path": tuple(_tile_fact(tile) for tile in self.path),
            "path_length": len(self.path),
            "ok": self.ok,
            "reason": self.reason,
            "method": self.method,
            "visited_tiles": self.visited_tiles,
            "max_search": self.max_search,
            "max_steps": self.max_steps,
        }


def blocking_footprint_tiles(origin: Tile, obj: OholObject) -> tuple[Tile, ...]:
    """Tiles blocked by an object's collision footprint.

    OHOL object files expose left/right blocking radii on the x-axis. Keep this
    footprint horizontal so tall-looking sprites do not over-block tight paths.
    """
    if not obj.blocks_walking:
        return ()
    left = max(0, int(obj.left_blocking_radius))
    right = max(0, int(obj.right_blocking_radius))
    if left == 0 and right == 0:
        return (origin,)
    tiles: list[Tile] = []
    for dx in range(-left, right + 1):
        tiles.append(Tile(origin.x + dx, origin.y))
    return tuple(tiles)


def tile_blocks_walking(
    tile: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
) -> bool:
    object_id = tile_objects.get(tile)
    if object_id is not None:
        obj = objects.get(object_id)
        if bool(obj and obj.blocks_walking):
            return True

    for object_tile, object_id in tile_objects.items():
        if object_tile == tile:
            continue
        obj = objects.get(object_id)
        if obj is None or not obj.blocks_walking:
            continue
        if tile in blocking_footprint_tiles(object_tile, obj):
            return True
    return False


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


def _bfs_parent_map(
    start: Tile,
    target: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    max_search: int,
    blocked_tiles: set[Tile],
) -> tuple[dict[Tile, Tile | None], int, bool]:
    parent: dict[Tile, Tile | None] = {start: None}
    queue: deque[Tile] = deque([start])
    visited = 0
    found = False
    while queue:
        current = queue.popleft()
        visited += 1
        if current.distance_to(start) > max_search:
            continue
        if current == target:
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
                blocked_tiles=blocked_tiles,
            ):
                continue
            parent[neighbor] = current
            queue.append(neighbor)
    return parent, visited, found


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

    preferred = _diagonal_step_toward(start, effective_target)
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
    parent, _, found = _bfs_parent_map(
        start,
        effective_target,
        tile_objects,
        objects,
        max_search=max_search,
        blocked_tiles=blocked,
    )

    if not found:
        return None

    step = effective_target
    while parent[step] is not None and parent[step] != start:
        step = parent[step]
    if parent.get(step) != start:
        return None
    return step


def walkable_path(
    start: Tile,
    target: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    max_search: int = 48,
    max_steps: int = 6,
    blocked_tiles: set[Tile] | None = None,
) -> tuple[Tile, ...] | None:
    """Return a short walkable path from start toward target."""
    result = walkable_path_with_diagnostics(
        start,
        target,
        tile_objects,
        objects,
        max_search=max_search,
        max_steps=max_steps,
        blocked_tiles=blocked_tiles,
    )
    return result.path if result.ok else None


def walkable_path_with_diagnostics(
    start: Tile,
    target: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    max_search: int = 48,
    max_steps: int = 6,
    blocked_tiles: set[Tile] | None = None,
) -> PathDiagnostics:
    """Return a short walkable path plus human-readable planning context."""
    if max_steps <= 0:
        return PathDiagnostics(
            start=start,
            target=target,
            effective_target=start,
            path=(),
            ok=True,
            reason="no steps requested",
            method="none",
            max_search=max_search,
            max_steps=max_steps,
        )
    if start == target:
        return PathDiagnostics(
            start=start,
            target=target,
            effective_target=target,
            path=(),
            ok=True,
            reason="already at target",
            method="none",
            max_search=max_search,
            max_steps=max_steps,
        )
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
            return PathDiagnostics(
                start=start,
                target=target,
                effective_target=None,
                path=(),
                ok=False,
                reason="target and adjacent approach tiles blocked",
                method="target-resolution",
                max_search=max_search,
                max_steps=max_steps,
            )
        effective_target = resolved

    preferred = _straight_path_prefix(
        start,
        effective_target,
        tile_objects,
        objects,
        max_steps=max_steps,
        blocked_tiles=blocked_tiles,
    )
    if preferred:
        return PathDiagnostics(
            start=start,
            target=target,
            effective_target=effective_target,
            path=preferred,
            ok=True,
            reason="clear straight prefix",
            method="straight",
            max_search=max_search,
            max_steps=max_steps,
        )

    blocked = blocked_tiles or set()
    parent, visited, found = _bfs_parent_map(
        start,
        effective_target,
        tile_objects,
        objects,
        max_search=max_search,
        blocked_tiles=blocked,
    )

    if not found:
        return PathDiagnostics(
            start=start,
            target=target,
            effective_target=effective_target,
            path=(),
            ok=False,
            reason="no route within search radius",
            method="bfs",
            visited_tiles=visited,
            max_search=max_search,
            max_steps=max_steps,
        )

    path: list[Tile] = []
    step = effective_target
    while parent[step] is not None:
        path.append(step)
        step = parent[step]
    path.reverse()
    truncated = tuple(path[:max_steps])
    return PathDiagnostics(
        start=start,
        target=target,
        effective_target=effective_target,
        path=truncated,
        ok=True,
        reason="bfs route found",
        method="bfs",
        visited_tiles=visited,
        max_search=max_search,
        max_steps=max_steps,
    )


def _straight_path_prefix(
    start: Tile,
    target: Tile,
    tile_objects: dict[Tile, int],
    objects: dict[int, OholObject],
    *,
    max_steps: int,
    blocked_tiles: set[Tile] | None = None,
) -> tuple[Tile, ...]:
    current = start
    path: list[Tile] = []
    for _ in range(max_steps):
        step = _diagonal_step_toward(current, target)
        if step == current:
            break
        if not can_step_to(
            current,
            step,
            tile_objects,
            objects,
            blocked_tiles=blocked_tiles,
        ):
            break
        path.append(step)
        current = step
        if current == target:
            break
    return tuple(path)


def _diagonal_step_toward(start: Tile, target: Tile) -> Tile:
    if start == target:
        return start
    dx = target.x - start.x
    dy = target.y - start.y
    return Tile(
        start.x + _sign(dx),
        start.y + _sign(dy),
    )


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _tile_fact(tile: Tile) -> dict[str, int]:
    return {"x": tile.x, "y": tile.y}
