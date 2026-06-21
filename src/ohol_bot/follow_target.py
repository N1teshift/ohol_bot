from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from .model import Observation, PlayerState, Tile
from .tiles import chebyshev, tile_set_from_facts

if TYPE_CHECKING:
    from .movement_policy import MovementFollowPolicy


def score_follow_candidate(
    tile: Tile,
    *,
    start: Tile,
    blocked: set[Tile],
    avoid_targets: set[Tile],
    current_target: Tile | None,
) -> dict[str, object]:
    distance = reachable_distance(start, tile, blocked)
    reachable = distance is not None
    path_cost = distance if distance is not None else 10_000
    score = (
        0 if reachable else 1,
        1 if tile in avoid_targets else 0,
        path_cost,
        chebyshev(tile, start),
        0 if tile == current_target else 1,
        tile.x,
        tile.y,
    )
    return {
        "tile": tile,
        "reachable": reachable,
        "distance": distance,
        "score": score,
        "avoid": tile in avoid_targets,
    }


def candidate_fact(candidate: dict[str, object]) -> dict[str, object]:
    tile = candidate["tile"]
    assert isinstance(tile, Tile)
    return {
        "x": tile.x,
        "y": tile.y,
        "reachable": bool(candidate["reachable"]),
        "distance": candidate["distance"],
        "avoid": bool(candidate["avoid"]),
    }


def reachable_distance(start: Tile, target: Tile, blocked: set[Tile]) -> int | None:
    if target in blocked:
        return None
    if start == target:
        return 0
    parent_distance: dict[Tile, int] = {start: 0}
    queue: deque[Tile] = deque([start])
    while queue:
        current = queue.popleft()
        distance = parent_distance[current]
        if distance > 48:
            continue
        for neighbor in neighbor_tiles(current):
            if neighbor in parent_distance:
                continue
            if not can_step_to_known(current, neighbor, blocked):
                continue
            if neighbor == target:
                return distance + 1
            parent_distance[neighbor] = distance + 1
            queue.append(neighbor)
    return None


def neighbor_tiles(tile: Tile) -> tuple[Tile, ...]:
    return (
        Tile(tile.x + 1, tile.y),
        Tile(tile.x - 1, tile.y),
        Tile(tile.x, tile.y + 1),
        Tile(tile.x, tile.y - 1),
        Tile(tile.x + 1, tile.y + 1),
        Tile(tile.x + 1, tile.y - 1),
        Tile(tile.x - 1, tile.y + 1),
        Tile(tile.x - 1, tile.y - 1),
    )


def can_step_to_known(from_tile: Tile, to_tile: Tile, blocked: set[Tile]) -> bool:
    if to_tile in blocked:
        return False
    dx = to_tile.x - from_tile.x
    dy = to_tile.y - from_tile.y
    if abs(dx) == 1 and abs(dy) == 1:
        if Tile(from_tile.x + dx, from_tile.y) in blocked:
            return False
        if Tile(from_tile.x, from_tile.y + dy) in blocked:
            return False
    return True


def follow_candidate_tiles(
    leader: PlayerState,
    blocked: set[Tile],
    desired_distance: int,
) -> list[Tile]:
    candidates: list[Tile] = []
    radius = desired_distance
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if max(abs(dx), abs(dy)) != radius:
                continue
            tile = Tile(leader.tile.x + dx, leader.tile.y + dy)
            if tile == leader.tile or tile in blocked:
                continue
            candidates.append(tile)
    return candidates


def target_is_still_reasonable(
    target: Tile,
    leader: PlayerState,
    blocked: set[Tile],
    desired_distance: int,
) -> bool:
    if target in blocked:
        return False
    return chebyshev(target, leader.tile) == desired_distance


def select_follow_target(
    policy: MovementFollowPolicy,
    observation: Observation,
    leader: PlayerState,
) -> Tile:
    blocked = tile_set_from_facts(observation.facts.get("blocked_tiles"))
    blocked.update(tile_set_from_facts(observation.facts.get("known_blocking_tiles")))
    avoid_targets = tile_set_from_facts(observation.facts.get("avoid_targets"))
    now_tick = observation.tick
    if (
        policy._current_target is not None
        and now_tick - policy._target_set_tick < policy.config.retarget_cooldown_ticks
        and target_is_still_reasonable(
            policy._current_target,
            leader,
            blocked,
            policy.config.desired_distance,
        )
    ):
        return policy._current_target

    candidates = follow_candidate_tiles(
        leader,
        blocked,
        policy.config.desired_distance,
    )
    scored = [
        score_follow_candidate(
            candidate,
            start=observation.self.tile,
            blocked=blocked,
            avoid_targets=avoid_targets,
            current_target=policy._current_target,
        )
        for candidate in candidates
    ]
    scored.sort(key=lambda candidate: candidate["score"])
    observation.facts["follow_candidate_tiles"] = tuple(
        candidate_fact(candidate) for candidate in scored[:8]
    )
    reachable = [candidate for candidate in scored if candidate["reachable"]]
    selected = reachable[0] if reachable else (scored[0] if scored else None)
    target = (
        selected["tile"]
        if isinstance(selected, dict) and isinstance(selected.get("tile"), Tile)
        else observation.self.tile
    )
    policy._current_target = target
    policy._target_set_tick = now_tick
    return target
