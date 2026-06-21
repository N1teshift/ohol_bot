from __future__ import annotations

from collections.abc import Callable

from .action_pending import PendingAction
from .model import Action, ActionType, ObjectState, Observation, Tile
from .tiles import is_orthogonally_adjacent, tile_set_from_facts


def can_interact_with_tile(from_tile: Tile, target_tile: Tile) -> bool:
    """OHOL USE/PICK_UP/DROP-on-target require same tile or N/S/E/W adjacency."""
    if from_tile == target_tile:
        return True
    return is_orthogonally_adjacent(from_tile, target_tile)


def approach_tile_orthogonal(observation: Observation, target: Tile) -> Tile | None:
    """Nearest walkable tile orthogonally beside target."""
    blocked = tile_set_from_facts(observation.facts.get("blocked_tiles"))
    blocked.update(tile_set_from_facts(observation.facts.get("known_blocking_tiles")))
    occupied = {player.tile for player in observation.nearby_players}
    best: Tile | None = None
    best_distance: int | None = None
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        candidate = Tile(target.x + dx, target.y + dy)
        if candidate in blocked or candidate in occupied:
            continue
        distance = observation.self.tile.distance_to(candidate)
        if best is None or distance < best_distance:
            best = candidate
            best_distance = distance
    return best


def decide_navigate_to_interact(
    observation: Observation,
    target: Tile,
    *,
    target_name: str,
    reason_prefix: str = "move beside",
) -> tuple[Action, str]:
    if can_interact_with_tile(observation.self.tile, target):
        return Action(ActionType.WAIT, {"ticks": 1}), f"beside {target_name}"
    approach = approach_tile_orthogonal(observation, target)
    if approach is None:
        return (
            Action(ActionType.WAIT, {"ticks": 1}),
            f"no walkable tile beside {target_name}",
        )
    reason = f"{reason_prefix} {target_name}"
    return Action(ActionType.MOVE_TO, {"x": approach.x, "y": approach.y}), reason


def drop_candidates(tile: Tile) -> tuple[Tile, ...]:
    offsets = (
        (0, 0),
        (0, 1),
        (1, 0),
        (0, -1),
        (-1, 0),
        (1, 1),
        (-1, 1),
        (1, -1),
        (-1, -1),
    )
    return tuple(Tile(tile.x + dx, tile.y + dy) for dx, dy in offsets)


def select_drop_tile(observation: Observation) -> Tile | None:
    occupied = {obj.tile for obj in observation.nearby_objects}
    occupied.update(player.tile for player in observation.nearby_players)
    blocked = tile_set_from_facts(observation.facts.get("blocked_tiles"))
    for tile in drop_candidates(observation.self.tile):
        if tile in occupied or tile in blocked:
            continue
        return tile
    return None


def ensure_empty_hands(
    observation: Observation,
    *,
    held_name: str,
    drop_settle_reason: Callable[[Observation], str | None],
    drop_retry_reason: Callable[[Observation, Tile], str | None],
    note_drop_attempt: Callable[[Observation, Tile], None],
    clear_drop_state: Callable[[], None],
    reason_prefix: str = "drop held",
    reason_suffix: str | None = None,
) -> tuple[Action | None, str | None]:
    """Return a blocking action and reason while clearing held items, or (None, None)."""
    if observation.self.held_object_id is None and not observation.self.is_holding_food:
        settle_reason = drop_settle_reason(observation)
        if settle_reason is not None:
            return Action(ActionType.WAIT, {"ticks": 1}), settle_reason
        clear_drop_state()
        return None, None

    drop_tile = select_drop_tile(observation)
    if drop_tile is None:
        return (
            Action(ActionType.WAIT, {"ticks": 1}),
            f"cannot drop held {held_name}",
        )

    retry_reason = drop_retry_reason(observation, drop_tile)
    if retry_reason is not None:
        return Action(ActionType.WAIT, {"ticks": 1}), retry_reason

    note_drop_attempt(observation, drop_tile)
    if reason_suffix:
        drop_reason = f"{reason_prefix} {held_name} {reason_suffix}"
    else:
        drop_reason = f"{reason_prefix} {held_name}"
    return (
        Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y}),
        drop_reason,
    )


def maybe_sync_pickup_state(
    observation: Observation,
    source_tile: Tile,
    *,
    pending: PendingAction,
    clear_pickup: Callable[[], None],
) -> None:
    if observation.self.held_pending:
        return
    if observation.self.held_object_id is not None or observation.self.is_holding_food:
        clear_pickup()
        return
    if (
        pending.tile is not None
        and pending.tile != source_tile
        and not can_interact_with_tile(observation.self.tile, pending.tile)
    ):
        clear_pickup()


def decide_pickup_action(
    observation: Observation,
    target: ObjectState,
    *,
    pending: PendingAction,
    pickup_retry_reason: Callable[[Observation, Tile], str | None],
    note_pickup_attempt: Callable[[Observation, Tile], None],
    reason_prefix: str = "pick up",
    reason_suffix: str | None = None,
) -> tuple[Action, str]:
    if not observation.self.is_stationary:
        return Action(ActionType.WAIT, {"ticks": 1}), "wait stationary for pickup"

    retry_reason = pickup_retry_reason(observation, target.tile)
    if retry_reason is not None:
        return Action(ActionType.WAIT, {"ticks": 1}), retry_reason

    note_pickup_attempt(observation, target.tile)
    if reason_suffix:
        reason = f"{reason_prefix} {target.name} {reason_suffix}"
    else:
        reason = f"{reason_prefix} {target.name}"
    return (
        Action(ActionType.PICK_UP, {"x": target.tile.x, "y": target.tile.y}),
        reason,
    )


def decide_navigate_or_pickup(
    observation: Observation,
    target: ObjectState,
    *,
    pending: PendingAction,
    pickup_retry_reason: Callable[[Observation, Tile], str | None],
    note_pickup_attempt: Callable[[Observation, Tile], None],
    clear_pickup: Callable[[], None],
    reason_prefix: str = "pick up",
    reason_suffix: str | None = None,
) -> tuple[Action, str]:
    maybe_sync_pickup_state(
        observation,
        target.tile,
        pending=pending,
        clear_pickup=clear_pickup,
    )
    if can_interact_with_tile(observation.self.tile, target.tile):
        return decide_pickup_action(
            observation,
            target,
            pending=pending,
            pickup_retry_reason=pickup_retry_reason,
            note_pickup_attempt=note_pickup_attempt,
            reason_prefix=reason_prefix,
            reason_suffix=reason_suffix,
        )
    approach = approach_tile_orthogonal(observation, target.tile)
    if approach is None:
        return (
            Action(ActionType.WAIT, {"ticks": 1}),
            f"no walkable tile beside {target.name}",
        )
    return (
        Action(ActionType.MOVE_TO, {"x": approach.x, "y": approach.y}),
        f"move beside {target.name}",
    )
