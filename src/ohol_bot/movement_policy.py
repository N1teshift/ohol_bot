from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

from .model import Action, ActionType, ObjectState, Observation, PlayerState, Tile
from .policy import Policy


@dataclass(frozen=True, slots=True)
class FollowConfig:
    desired_distance: int = 1
    retarget_cooldown_ticks: int = 4
    collect_pickup_retry_cooldown_ticks: int = 12
    collect_drop_retry_cooldown_ticks: int = 12
    collect_drop_settle_ticks: int = 3


class MovementFollowPolicy(Policy):
    """Movement-first policy with idle and chat-driven follow/collect modes."""

    def __init__(self, config: FollowConfig | None = None) -> None:
        self.config = config or FollowConfig()
        self.mode = "idle"
        self.leader_id: int | None = None
        self._last_chat_sequence = 0
        self._current_target: Tile | None = None
        self._target_set_tick = -10_000
        self._last_leader_tile: Tile | None = None
        self.collect_requested_by: int | None = None
        self.collect_names: frozenset[str] = frozenset()
        self._collect_pickup_tile: Tile | None = None
        self._collect_pickup_sent_tick = -10_000
        self._collect_pickup_attempts = 0
        self._collect_drop_tile: Tile | None = None
        self._collect_drop_sent_tick = -10_000
        self._collect_drop_attempts = 0

    def decide(self, observation: Observation) -> Action:
        command_reason = self._consume_chat_commands(observation)
        if self.mode == "collect":
            return self._decide_collect(observation, command_reason)

        if self.mode != "follow" or self.leader_id is None:
            self._current_target = None
            self._annotate(
                observation,
                reason=command_reason or "idle",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        leader = self._leader(observation)
        if leader is None:
            self._annotate(
                observation,
                reason="leader not visible",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        distance = _chebyshev(observation.self.tile, leader.tile)
        self._last_leader_tile = leader.tile
        if distance <= self.config.desired_distance:
            self._current_target = None
            self._annotate(
                observation,
                leader=leader,
                leader_distance=distance,
                reason="close enough to leader",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        target = self._select_follow_target(observation, leader)
        self._annotate(
            observation,
            leader=leader,
            leader_distance=distance,
            target=target,
            reason=command_reason or "move adjacent to leader",
        )
        if target == observation.self.tile:
            return Action(ActionType.WAIT, {"ticks": 1})
        return Action(ActionType.MOVE_TO, {"x": target.x, "y": target.y})

    def _consume_chat_commands(self, observation: Observation) -> str | None:
        reason = None
        for event in _chat_events(observation):
            sequence = int(event.get("sequence", 0))
            if sequence <= self._last_chat_sequence:
                continue
            self._last_chat_sequence = sequence
            player_id = _optional_int(event.get("player_id"))
            text = str(event.get("text", "")).strip().lower()
            if player_id is None or player_id == observation.self.player_id:
                continue
            if text == "follow":
                self.mode = "follow"
                self.leader_id = player_id
                self._current_target = None
                self._clear_collect()
                reason = f"follow command from player {player_id}"
            elif text in {"stop follow", "stop following", "stop collect", "idle"}:
                if self.leader_id is None or self.leader_id == player_id:
                    self.mode = "idle"
                    self.leader_id = None
                    self._current_target = None
                    self._clear_collect()
                    reason = f"stop command from player {player_id}"
            else:
                collect_name = _parse_collect_command(text)
                if collect_name is not None:
                    self.mode = "collect"
                    self.leader_id = None
                    self._current_target = None
                    self._clear_collect_pickup()
                    self.collect_requested_by = player_id
                    self.collect_names = frozenset({collect_name})
                    reason = f"collect command from player {player_id}"
        return reason

    def _decide_collect(
        self,
        observation: Observation,
        command_reason: str | None,
    ) -> Action:
        held_name = observation.self.held_object_name or "object"
        if observation.self.held_pending:
            self._annotate(
                observation,
                reason="collect pickup pending",
                collect_reason="collect pickup pending",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            if _is_holding_collect_target(observation, self.collect_names):
                reason = f"collect complete holding {held_name}"
                self._clear_collect()
                self.mode = "idle"
                self._annotate(
                    observation,
                    reason=reason,
                    collect_reason=reason,
                )
                return Action(ActionType.WAIT, {"ticks": 1})

            drop_tile = _select_drop_tile(observation)
            if drop_tile is None:
                self._annotate(
                    observation,
                    reason=f"collect cannot drop held {held_name}",
                    collect_reason=f"collect cannot drop held {held_name}",
                )
                return Action(ActionType.WAIT, {"ticks": 1})

            retry_reason = self._collect_drop_retry_reason(observation, drop_tile)
            if retry_reason is not None:
                self._annotate(
                    observation,
                    reason=retry_reason,
                    collect_reason=retry_reason,
                )
                return Action(ActionType.WAIT, {"ticks": 1})

            self._note_collect_drop_attempt(observation, drop_tile)
            reason = f"drop held {held_name} before collect"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

        settle_reason = self._collect_drop_settle_reason(observation)
        if settle_reason is not None:
            self._annotate(
                observation,
                reason=settle_reason,
                collect_reason=settle_reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        self._clear_collect_drop()

        target = _nearest_named_object(observation, self.collect_names)
        if target is None:
            self._annotate(
                observation,
                reason=command_reason or "collect target not visible",
                collect_reason=command_reason or "collect target not visible",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.tile == target.tile or _is_adjacent(
            observation.self.tile,
            target.tile,
        ):
            retry_reason = self._collect_pickup_retry_reason(observation, target.tile)
            if retry_reason is not None:
                self._annotate(
                    observation,
                    collect_target=target.tile,
                    reason=retry_reason,
                    collect_reason=retry_reason,
                    collect_target_name=target.name,
                )
                return Action(ActionType.WAIT, {"ticks": 1})

            self._note_collect_pickup_attempt(observation, target.tile)
            self._annotate(
                observation,
                collect_target=target.tile,
                reason=f"pick up {target.name}",
                collect_reason=f"pick up {target.name}",
                collect_target_name=target.name,
            )
            return Action(ActionType.PICK_UP, {"x": target.tile.x, "y": target.tile.y})

        self._annotate(
            observation,
            collect_target=target.tile,
            reason=command_reason or f"move to {target.name}",
            collect_reason=command_reason or f"move to {target.name}",
            collect_target_name=target.name,
        )
        return Action(ActionType.MOVE_TO, {"x": target.tile.x, "y": target.tile.y})

    def _clear_collect(self) -> None:
        self.collect_requested_by = None
        self.collect_names = frozenset()
        self._clear_collect_pickup()
        self._clear_collect_drop()

    def _clear_collect_pickup(self) -> None:
        self._collect_pickup_tile = None
        self._collect_pickup_sent_tick = -10_000
        self._collect_pickup_attempts = 0

    def _clear_collect_drop(self) -> None:
        self._collect_drop_tile = None
        self._collect_drop_sent_tick = -10_000
        self._collect_drop_attempts = 0

    def _collect_drop_retry_reason(
        self,
        observation: Observation,
        tile: Tile,
    ) -> str | None:
        if self._collect_drop_tile != tile:
            return None
        elapsed = observation.tick - self._collect_drop_sent_tick
        remaining = self.config.collect_drop_retry_cooldown_ticks - elapsed
        if remaining > 0:
            return f"collect drop retry wait {remaining}"
        return None

    def _collect_drop_settle_reason(self, observation: Observation) -> str | None:
        if self._collect_drop_tile is None:
            return None
        elapsed = observation.tick - self._collect_drop_sent_tick
        remaining = self.config.collect_drop_settle_ticks - elapsed
        if remaining > 0:
            return f"collect drop settle wait {remaining}"
        return None

    def _note_collect_drop_attempt(
        self,
        observation: Observation,
        tile: Tile,
    ) -> None:
        if self._collect_drop_tile != tile:
            self._collect_drop_tile = tile
            self._collect_drop_attempts = 0
        self._collect_drop_attempts += 1
        self._collect_drop_sent_tick = observation.tick

    def _collect_pickup_retry_reason(
        self,
        observation: Observation,
        tile: Tile,
    ) -> str | None:
        if self._collect_pickup_tile != tile:
            return None
        elapsed = observation.tick - self._collect_pickup_sent_tick
        remaining = self.config.collect_pickup_retry_cooldown_ticks - elapsed
        if remaining > 0:
            return f"collect pickup retry wait {remaining}"
        return None

    def _note_collect_pickup_attempt(
        self,
        observation: Observation,
        tile: Tile,
    ) -> None:
        if self._collect_pickup_tile != tile:
            self._collect_pickup_tile = tile
            self._collect_pickup_attempts = 0
        self._collect_pickup_attempts += 1
        self._collect_pickup_sent_tick = observation.tick

    def _leader(self, observation: Observation) -> PlayerState | None:
        if self.leader_id is None:
            return None
        for player in observation.nearby_players:
            if player.player_id == self.leader_id:
                return player
        return None

    def _select_follow_target(
        self,
        observation: Observation,
        leader: PlayerState,
    ) -> Tile:
        blocked = _tile_set(observation.facts.get("blocked_tiles"))
        blocked.update(_tile_set(observation.facts.get("known_blocking_tiles")))
        avoid_targets = _tile_set(observation.facts.get("avoid_targets"))
        now_tick = observation.tick
        if (
            self._current_target is not None
            and now_tick - self._target_set_tick < self.config.retarget_cooldown_ticks
            and self._target_is_still_reasonable(self._current_target, leader, blocked)
        ):
            return self._current_target

        candidates = self._candidate_tiles(leader, blocked)
        scored = [
            _score_follow_candidate(
                candidate,
                start=observation.self.tile,
                blocked=blocked,
                avoid_targets=avoid_targets,
                current_target=self._current_target,
            )
            for candidate in candidates
        ]
        scored.sort(key=lambda candidate: candidate["score"])
        observation.facts["follow_candidate_tiles"] = tuple(
            _candidate_fact(candidate) for candidate in scored[:8]
        )
        reachable = [candidate for candidate in scored if candidate["reachable"]]
        selected = reachable[0] if reachable else (scored[0] if scored else None)
        target = (
            selected["tile"]
            if isinstance(selected, dict) and isinstance(selected.get("tile"), Tile)
            else observation.self.tile
        )
        self._current_target = target
        self._target_set_tick = now_tick
        return target

    def _candidate_tiles(
        self,
        leader: PlayerState,
        blocked: set[Tile],
    ) -> list[Tile]:
        candidates: list[Tile] = []
        radius = self.config.desired_distance
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                tile = Tile(leader.tile.x + dx, leader.tile.y + dy)
                if tile == leader.tile or tile in blocked:
                    continue
                candidates.append(tile)
        return candidates

    def _target_is_still_reasonable(
        self,
        target: Tile,
        leader: PlayerState,
        blocked: set[Tile],
    ) -> bool:
        if target in blocked:
            return False
        distance = _chebyshev(target, leader.tile)
        return distance == self.config.desired_distance

    def _annotate(
        self,
        observation: Observation,
        *,
        leader: PlayerState | None = None,
        leader_distance: int | None = None,
        target: Tile | None = None,
        reason: str,
        collect_reason: str | None = None,
        collect_target: Tile | None = None,
        collect_target_name: str | None = None,
    ) -> None:
        observation.facts["movement_mode"] = self.mode
        observation.facts["follow_leader_id"] = self.leader_id
        observation.facts["follow_reason"] = reason
        observation.facts["follow_target"] = (
            {"x": target.x, "y": target.y} if target is not None else None
        )
        observation.facts["follow_leader_tile"] = (
            {"x": leader.tile.x, "y": leader.tile.y} if leader is not None else None
        )
        observation.facts["follow_leader_distance"] = leader_distance
        observation.facts["follow_last_chat_sequence"] = self._last_chat_sequence
        observation.facts["collect_requested_by"] = self.collect_requested_by
        observation.facts["collect_names"] = tuple(sorted(self.collect_names))
        observation.facts["collect_target_name"] = collect_target_name
        observation.facts["collect_target"] = (
            {"x": collect_target.x, "y": collect_target.y}
            if collect_target is not None
            else None
        )
        observation.facts["collect_reason"] = collect_reason


def _chat_events(observation: Observation) -> tuple[Mapping[str, Any], ...]:
    raw = observation.facts.get("chat_events")
    if not isinstance(raw, tuple):
        return ()
    return tuple(event for event in raw if isinstance(event, Mapping))


def _parse_collect_command(text: str) -> str | None:
    prefix = "collect "
    if not text.startswith(prefix):
        return None
    name = text[len(prefix):].strip()
    return name or None


def _nearest_named_object(
    observation: Observation,
    names: frozenset[str],
) -> ObjectState | None:
    if not names:
        return None
    candidates = [
        obj for obj in observation.nearby_objects if _normalize_name(obj.name) in names
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda obj: observation.self.tile.distance_to(obj.tile))


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _is_holding_collect_target(
    observation: Observation,
    names: frozenset[str],
) -> bool:
    held_name = observation.self.held_object_name
    if held_name is None:
        return False
    return _normalize_name(held_name) in names


def _select_drop_tile(observation: Observation) -> Tile | None:
    occupied = {obj.tile for obj in observation.nearby_objects}
    occupied.update(player.tile for player in observation.nearby_players)
    blocked = _tile_set(observation.facts.get("blocked_tiles"))
    for tile in _drop_candidates(observation.self.tile):
        if tile in occupied or tile in blocked:
            continue
        return tile
    return None


def _drop_candidates(tile: Tile) -> tuple[Tile, ...]:
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


def _tile_set(raw: Any) -> set[Tile]:
    if not isinstance(raw, tuple):
        return set()
    return {Tile(int(x), int(y)) for x, y in raw}


def _score_follow_candidate(
    tile: Tile,
    *,
    start: Tile,
    blocked: set[Tile],
    avoid_targets: set[Tile],
    current_target: Tile | None,
) -> dict[str, object]:
    distance = _reachable_distance(start, tile, blocked)
    reachable = distance is not None
    path_cost = distance if distance is not None else 10_000
    score = (
        0 if reachable else 1,
        1 if tile in avoid_targets else 0,
        path_cost,
        _chebyshev(tile, start),
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


def _candidate_fact(candidate: dict[str, object]) -> dict[str, object]:
    tile = candidate["tile"]
    assert isinstance(tile, Tile)
    return {
        "x": tile.x,
        "y": tile.y,
        "reachable": bool(candidate["reachable"]),
        "distance": candidate["distance"],
        "avoid": bool(candidate["avoid"]),
    }


def _reachable_distance(start: Tile, target: Tile, blocked: set[Tile]) -> int | None:
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
        for neighbor in _neighbor_tiles(current):
            if neighbor in parent_distance:
                continue
            if not _can_step_to_known(current, neighbor, blocked):
                continue
            if neighbor == target:
                return distance + 1
            parent_distance[neighbor] = distance + 1
            queue.append(neighbor)
    return None


def _neighbor_tiles(tile: Tile) -> tuple[Tile, ...]:
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


def _can_step_to_known(from_tile: Tile, to_tile: Tile, blocked: set[Tile]) -> bool:
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


def _optional_int(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _chebyshev(a: Tile, b: Tile) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _is_adjacent(a: Tile, b: Tile) -> bool:
    return max(abs(a.x - b.x), abs(a.y - b.y)) == 1
