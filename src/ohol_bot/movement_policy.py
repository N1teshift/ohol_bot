from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model import Action, ActionType, Observation, PlayerState, Tile
from .policy import Policy


@dataclass(frozen=True, slots=True)
class FollowConfig:
    desired_distance: int = 1
    retarget_cooldown_ticks: int = 4


class MovementFollowPolicy(Policy):
    """Movement-first policy with idle and chat-driven follow modes."""

    def __init__(self, config: FollowConfig | None = None) -> None:
        self.config = config or FollowConfig()
        self.mode = "idle"
        self.leader_id: int | None = None
        self._last_chat_sequence = 0
        self._current_target: Tile | None = None
        self._target_set_tick = -10_000
        self._last_leader_tile: Tile | None = None

    def decide(self, observation: Observation) -> Action:
        command_reason = self._consume_chat_commands(observation)
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
                reason = f"follow command from player {player_id}"
            elif text in {"stop follow", "stop following", "idle"}:
                if self.leader_id is None or self.leader_id == player_id:
                    self.mode = "idle"
                    self.leader_id = None
                    self._current_target = None
                    reason = f"stop command from player {player_id}"
        return reason

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
        avoid_targets = _tile_set(observation.facts.get("avoid_targets"))
        now_tick = observation.tick
        if (
            self._current_target is not None
            and now_tick - self._target_set_tick < self.config.retarget_cooldown_ticks
            and self._target_is_still_reasonable(self._current_target, leader, blocked)
        ):
            return self._current_target

        candidates = self._candidate_tiles(leader, blocked)
        candidates.sort(
            key=lambda tile: (
                1 if tile in avoid_targets else 0,
                _chebyshev(tile, observation.self.tile),
                0 if tile == self._current_target else 1,
                tile.x,
                tile.y,
            )
        )
        target = candidates[0] if candidates else observation.self.tile
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


def _chat_events(observation: Observation) -> tuple[Mapping[str, Any], ...]:
    raw = observation.facts.get("chat_events")
    if not isinstance(raw, tuple):
        return ()
    return tuple(event for event in raw if isinstance(event, Mapping))


def _tile_set(raw: Any) -> set[Tile]:
    if not isinstance(raw, tuple):
        return set()
    return {Tile(int(x), int(y)) for x, y in raw}


def _optional_int(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _chebyshev(a: Tile, b: Tile) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))
