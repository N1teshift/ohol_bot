from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

from .camp_depot import camp_layout_from_facts
from .model import Action, ActionType, ObjectState, Observation, PlayerState, Tile
from .danger import base_object_name
from .home import DEFAULT_HOME_AREA_RADIUS, find_home_center_near
from .policy import Policy
from .speech import fit_say_from_candidates, fit_say_text


@dataclass(frozen=True, slots=True)
class FollowConfig:
    desired_distance: int = 1
    retarget_cooldown_ticks: int = 4
    collect_pickup_retry_cooldown_ticks: int = 3
    collect_drop_retry_cooldown_ticks: int = 12
    collect_drop_settle_ticks: int = 3
    collect_stack_deposit_settle_ticks: int = 3
    stack_source_retarget_cooldown_ticks: int = 6


_CHAT_REPLY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "hello": ("HELLO", "HI", "H"),
    "hi": ("HI", "H"),
    "hey": ("HELLO", "HI", "H"),
}


@dataclass(slots=True)
class StackCollectState:
    requested_by: int
    item_name: str
    item_names: frozenset[str]
    pile_names: frozenset[str]
    depot_origin: Tile | None
    depot_tile: Tile | None
    loose_object_id: int | None = None
    pile_object_id: int | None = None
    depot_target_ids: tuple[int, ...] = ()
    source_target_ids: tuple[int, ...] = ()
    desired_count: int = 6
    deposited_count: int = 0
    drop_only: bool = False
    pending_deposit_tile: Tile | None = None
    pending_deposit_sent_tick: int = -10_000


@dataclass(slots=True)
class CampSlotProgress:
    slot_id: int
    state: StackCollectState


@dataclass(slots=True)
class CampStockState:
    requested_by: int
    slots: tuple[CampSlotProgress, ...]


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
        self.collect_stack: StackCollectState | None = None
        self._stack_source_tile: Tile | None = None
        self._stack_source_set_tick = -10_000
        self.make_sharp_stone_requested_by: int | None = None
        self.stock_camp_requested_by: int | None = None
        self.camp_stock: CampStockState | None = None
        self._pending_say: str | None = None

    def decide(self, observation: Observation) -> Action:
        command_reason = self._consume_chat_commands(observation)
        if self._pending_say is not None and observation.self.is_stationary:
            text = fit_say_text(self._pending_say, age=observation.self.age)
            self._pending_say = None
            if text is not None:
                self._annotate(observation, reason=f"chat reply: {text}")
                return Action(ActionType.SAY, {"text": text})
        if self.mode == "collect_stack":
            return self._decide_collect_stack(observation, command_reason)
        if self.mode == "stock_camp":
            return self._decide_stock_camp(observation, command_reason)
        if self.mode == "collect":
            return self._decide_collect(observation, command_reason)
        if self.mode == "make_sharp_stone":
            return self._decide_make_sharp_stone(observation, command_reason)

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
                self._reset_task_modes()
                self.mode = "follow"
                self.leader_id = player_id
                self._current_target = None
                reason = f"follow command from player {player_id}"
            elif text in {
                "stop follow",
                "stop following",
                "stop collect",
                "stop make sharp stone",
                "stop make",
                "idle",
            }:
                if (
                    self.leader_id is None
                    or self.leader_id == player_id
                    or self.make_sharp_stone_requested_by == player_id
                    or self.collect_requested_by == player_id
                    or self.stock_camp_requested_by == player_id
                ):
                    self.mode = "idle"
                    self.leader_id = None
                    self._current_target = None
                    self._clear_collect()
                    reason = f"stop command from player {player_id}"
            elif text == "stock camp":
                layout = camp_layout_from_facts(observation.facts.get("camp_layout"))
                if layout is None and observation.home is not None:
                    from .camp_depot import build_camp_layout

                    layout = build_camp_layout(observation.home)
                if layout is None:
                    reason = f"stock camp rejected: home not set (player {player_id})"
                else:
                    self._reset_task_modes()
                    self.mode = "stock_camp"
                    self.stock_camp_requested_by = player_id
                    self.camp_stock = _camp_stock_state_from_layout(
                        observation,
                        layout,
                        requested_by=player_id,
                    )
                    reason = f"stock camp from player {player_id}"
            elif text == "make sharp stone":
                self._reset_task_modes()
                self.mode = "make_sharp_stone"
                self.make_sharp_stone_requested_by = player_id
                reason = f"make sharp stone from player {player_id}"
            elif text == "set home here":
                speaker_tile = _speaker_tile(observation, player_id)
                if speaker_tile is not None:
                    center = find_home_center_near(observation, speaker_tile)
                    if center is not None:
                        home_tile = center.tile
                        center_name = base_object_name(center.name)
                        observation.facts["set_home_tile"] = {
                            "x": home_tile.x,
                            "y": home_tile.y,
                        }
                        observation.facts["set_home_radius"] = DEFAULT_HOME_AREA_RADIUS
                        observation.facts["set_home_center_name"] = center_name
                        reason = (
                            f"set home at {center_name} ({home_tile.x}, {home_tile.y}) "
                            f"from player {player_id}"
                        )
                    else:
                        observation.facts["set_home_tile"] = {
                            "x": speaker_tile.x,
                            "y": speaker_tile.y,
                        }
                        observation.facts["set_home_radius"] = DEFAULT_HOME_AREA_RADIUS
                        reason = (
                            f"set home from player {player_id} at "
                            f"({speaker_tile.x}, {speaker_tile.y}); no well/spring nearby"
                        )
            elif (reply := _chat_reply(text, observation.self.age)) is not None:
                self._pending_say = reply
                reason = f"chat greeting from player {player_id}"
            else:
                stack_item = _parse_collect_stack_command(text)
                if stack_item is not None:
                    self._reset_task_modes()
                    self.mode = "collect_stack"
                    speaker = _player_by_id(observation, player_id)
                    depot_origin = speaker.tile if speaker is not None else None
                    stack_rule = _resolve_stack_rule(observation, stack_item)
                    depot_tile = (
                        _select_stack_depot_tile(
                            observation,
                            depot_origin,
                            stack_rule,
                        )
                        if depot_origin is not None
                        else None
                    )
                    self.collect_stack = _stack_state_from_rule(
                        stack_rule,
                        requested_by=player_id,
                        depot_origin=depot_origin,
                        depot_tile=depot_tile,
                    )
                    reason = f"collect stack command from player {player_id}"
                    continue
                collect_name = _parse_collect_command(text)
                if collect_name is not None:
                    self._reset_task_modes()
                    self.mode = "collect"
                    self._clear_collect_pickup()
                    self.collect_requested_by = player_id
                    self.collect_names = frozenset({collect_name})
                    reason = f"collect command from player {player_id}"
        return reason

    def _decide_collect_stack(
        self,
        observation: Observation,
        command_reason: str | None,
    ) -> Action:
        state = self.collect_stack
        if state is None:
            self.mode = "idle"
            self._annotate(
                observation,
                reason="stack collect missing state",
                collect_reason="stack collect missing state",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        depot = state.depot_tile
        if depot is None:
            reason = command_reason or "stack depot unavailable"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        completed = self._maybe_note_stack_deposit_complete(observation, state)
        if completed:
            self._clear_collect_pickup()
            self._clear_collect_drop()

        if state.deposited_count >= state.desired_count:
            reason = f"stack complete {state.deposited_count}/{state.desired_count} {state.item_name}"
            self.mode = "idle"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.held_pending:
            reason = "stack pickup pending"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        settle_reason = self._collect_stack_deposit_settle_reason(observation, state)
        if settle_reason is not None:
            self._annotate(
                observation,
                reason=settle_reason,
                collect_reason=settle_reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            if _is_holding_collect_target(observation, state.item_names):
                if not _is_adjacent_or_same(observation.self.tile, depot):
                    reason = f"return to stack depot with {state.item_name}"
                    self._annotate(
                        observation,
                        collect_target=depot,
                        reason=reason,
                        collect_reason=reason,
                        collect_target_name=state.item_name,
                    )
                    return Action(ActionType.MOVE_TO, {"x": depot.x, "y": depot.y})

                depot_object = _object_at_tile(observation, depot)
                deposit_action, deposit_reason = _decide_stack_deposit_action(
                    observation,
                    state,
                    depot,
                    depot_object,
                    self,
                )
                if deposit_action is not None:
                    self._annotate(
                        observation,
                        collect_target=depot,
                        reason=deposit_reason,
                        collect_reason=deposit_reason,
                        collect_target_name=state.item_name,
                    )
                    return deposit_action

                reason = f"stack depot blocked by {depot_object.name if depot_object else 'unknown'}"
                self._annotate(
                    observation,
                    collect_target=depot,
                    reason=reason,
                    collect_reason=reason,
                    collect_target_name=state.item_name,
                )
                return Action(ActionType.WAIT, {"ticks": 1})

            drop_tile = _select_drop_tile(observation)
            if drop_tile is None:
                reason = f"stack cannot drop held {observation.self.held_object_name or 'object'}"
                self._annotate(
                    observation,
                    reason=reason,
                    collect_reason=reason,
                )
                return Action(ActionType.WAIT, {"ticks": 1})
            self._note_collect_drop_attempt(observation, drop_tile)
            held_name = observation.self.held_object_name or "object"
            reason = f"drop held {held_name} before stack collect"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

        target = _select_stack_source(observation, state, self)
        if target is None:
            if observation.self.tile != depot:
                reason = f"stack waiting: no visible {state.item_name}, return to depot"
                self._annotate(
                    observation,
                    collect_target=depot,
                    reason=reason,
                    collect_reason=reason,
                    collect_target_name=state.item_name,
                )
                return Action(ActionType.MOVE_TO, {"x": depot.x, "y": depot.y})
            reason = f"stack waiting: no visible {state.item_name}"
            self._annotate(
                observation,
                collect_target=depot,
                reason=reason,
                collect_reason=reason,
                collect_target_name=state.item_name,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if _is_adjacent_or_same(observation.self.tile, target.tile):
            pickup_action = self._decide_collect_pickup(
                observation,
                target,
                reason_prefix="pick up",
                reason_suffix="for stack",
            )
            if pickup_action is not None:
                return pickup_action

        reason = command_reason or f"move to {target.name} for stack"
        self._annotate(
            observation,
            collect_target=target.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=target.name,
        )
        return Action(ActionType.MOVE_TO, {"x": target.tile.x, "y": target.tile.y})

    def _decide_stock_camp(
        self,
        observation: Observation,
        command_reason: str | None,
    ) -> Action:
        camp = self.camp_stock
        if camp is None:
            self.mode = "idle"
            self._annotate(
                observation,
                reason="stock camp missing state",
                collect_reason="stock camp missing state",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        for slot in camp.slots:
            completed = self._maybe_note_stack_deposit_complete(
                observation,
                slot.state,
            )
            if completed:
                self._clear_collect_pickup()
                self._clear_collect_drop()

        if _camp_stock_complete(camp):
            reason = "stock camp complete"
            self.mode = "idle"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.held_pending:
            reason = "stock camp pickup pending"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        settle_reason = _camp_stock_deposit_settle_reason(self, observation, camp)
        if settle_reason is not None:
            self._annotate(
                observation,
                reason=settle_reason,
                collect_reason=settle_reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            active_slot = _camp_slot_for_held_item(observation, camp)
            if active_slot is not None:
                depot = active_slot.state.depot_tile
                if depot is None:
                    reason = "stock camp depot unavailable"
                    self._annotate(
                        observation,
                        reason=reason,
                        collect_reason=reason,
                    )
                    return Action(ActionType.WAIT, {"ticks": 1})
                if not _is_adjacent_or_same(observation.self.tile, depot):
                    reason = (
                        f"return to camp slot {active_slot.slot_id} "
                        f"with {active_slot.state.item_name}"
                    )
                    self._annotate(
                        observation,
                        collect_target=depot,
                        reason=reason,
                        collect_reason=reason,
                        collect_target_name=active_slot.state.item_name,
                    )
                    return Action(ActionType.MOVE_TO, {"x": depot.x, "y": depot.y})

                depot_object = _object_at_tile(observation, depot)
                deposit_action, deposit_reason = _decide_stack_deposit_action(
                    observation,
                    active_slot.state,
                    depot,
                    depot_object,
                    self,
                    slot_id=active_slot.slot_id,
                )
                if deposit_action is not None:
                    self._annotate(
                        observation,
                        collect_target=depot,
                        reason=deposit_reason,
                        collect_reason=deposit_reason,
                        collect_target_name=active_slot.state.item_name,
                    )
                    return deposit_action

                reason = (
                    f"camp slot {active_slot.slot_id} blocked by "
                    f"{depot_object.name if depot_object else 'unknown'}"
                )
                self._annotate(
                    observation,
                    collect_target=depot,
                    reason=reason,
                    collect_reason=reason,
                    collect_target_name=active_slot.state.item_name,
                )
                return Action(ActionType.WAIT, {"ticks": 1})

            drop_tile = _select_drop_tile(observation)
            if drop_tile is None:
                reason = (
                    f"stock camp cannot drop held "
                    f"{observation.self.held_object_name or 'object'}"
                )
                self._annotate(
                    observation,
                    reason=reason,
                    collect_reason=reason,
                )
                return Action(ActionType.WAIT, {"ticks": 1})
            self._note_collect_drop_attempt(observation, drop_tile)
            held_name = observation.self.held_object_name or "object"
            reason = f"drop held {held_name} before stock camp"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

        work = _select_camp_work(observation, camp, self)
        if work is None:
            reason = command_reason or "stock camp waiting: no visible camp items"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        _source, active_slot = work
        target = _select_stack_source(observation, active_slot.state, self)
        if target is None:
            reason = (
                f"stock camp waiting: no visible {active_slot.state.item_name} "
                f"for slot {active_slot.slot_id}"
            )
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
                collect_target_name=active_slot.state.item_name,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        if _is_adjacent_or_same(observation.self.tile, target.tile):
            pickup_action = self._decide_collect_pickup(
                observation,
                target,
                reason_prefix="pick up",
                reason_suffix=f"for camp slot {active_slot.slot_id}",
            )
            if pickup_action is not None:
                return pickup_action

        reason = (
            command_reason
            or f"move to {target.name} for camp slot {active_slot.slot_id}"
        )
        self._annotate(
            observation,
            collect_target=target.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=target.name,
        )
        return Action(ActionType.MOVE_TO, {"x": target.tile.x, "y": target.tile.y})

    def _maybe_note_stack_deposit_complete(
        self,
        observation: Observation,
        state: StackCollectState,
    ) -> bool:
        if state.pending_deposit_tile is None:
            return False
        elapsed = observation.tick - state.pending_deposit_sent_tick
        if elapsed < self.config.collect_stack_deposit_settle_ticks:
            return False
        if observation.self.held_pending:
            return False
        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            return False
        state.deposited_count += 1
        state.pending_deposit_tile = None
        state.pending_deposit_sent_tick = -10_000
        return True

    def _collect_stack_deposit_settle_reason(
        self,
        observation: Observation,
        state: StackCollectState,
    ) -> str | None:
        if state.pending_deposit_tile is None:
            return None
        elapsed = observation.tick - state.pending_deposit_sent_tick
        remaining = self.config.collect_stack_deposit_settle_ticks - elapsed
        if remaining > 0:
            return f"stack deposit settle wait {remaining}"
        return None

    def _note_stack_deposit_attempt(
        self,
        observation: Observation,
        state: StackCollectState,
        tile: Tile,
    ) -> None:
        state.pending_deposit_tile = tile
        state.pending_deposit_sent_tick = observation.tick

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
            pickup_action = self._decide_collect_pickup(
                observation,
                target,
                reason_prefix="pick up",
            )
            if pickup_action is not None:
                return pickup_action

        self._annotate(
            observation,
            collect_target=target.tile,
            reason=command_reason or f"move to {target.name}",
            collect_reason=command_reason or f"move to {target.name}",
            collect_target_name=target.name,
        )
        return Action(ActionType.MOVE_TO, {"x": target.tile.x, "y": target.tile.y})

    def _decide_make_sharp_stone(
        self,
        observation: Observation,
        command_reason: str | None,
    ) -> Action:
        if observation.self.held_pending:
            return self._craft_wait(observation, "craft action pending", command_reason)

        if _is_holding_sharp_stone(observation):
            reason = "make sharp stone complete"
            self._reset_task_modes()
            self.mode = "idle"
            self._annotate(observation, reason=reason, collect_reason=reason)
            return Action(ActionType.WAIT, {"ticks": 1})

        if _is_holding_loose_stone(observation):
            return self._decide_make_sharp_stone_on_rock(observation, command_reason)

        held_name = observation.self.held_object_name or "object"
        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            drop_tile = _select_drop_tile(observation)
            if drop_tile is None:
                return self._craft_wait(
                    observation,
                    f"cannot drop held {held_name}",
                    command_reason,
                )
            retry_reason = self._collect_drop_retry_reason(observation, drop_tile)
            if retry_reason is not None:
                return self._craft_wait(observation, retry_reason, command_reason)
            self._note_collect_drop_attempt(observation, drop_tile)
            reason = f"drop held {held_name} before make sharp stone"
            self._annotate(observation, reason=reason, collect_reason=reason)
            return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

        settle_reason = self._collect_drop_settle_reason(observation)
        if settle_reason is not None:
            return self._craft_wait(observation, settle_reason, command_reason)

        self._clear_collect_drop()

        stone = _nearest_loose_stone(observation)
        if stone is None:
            return self._craft_wait(
                observation,
                command_reason or "loose stone not visible",
                command_reason,
            )

        if observation.self.tile == stone.tile or _is_adjacent(
            observation.self.tile,
            stone.tile,
        ):
            pickup_action = self._decide_collect_pickup(
                observation,
                stone,
                reason_prefix="pick up",
            )
            if pickup_action is not None:
                return pickup_action

        reason = command_reason or f"move to {stone.name}"
        self._annotate(
            observation,
            collect_target=stone.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=stone.name,
        )
        return Action(ActionType.MOVE_TO, {"x": stone.tile.x, "y": stone.tile.y})

    def _decide_make_sharp_stone_on_rock(
        self,
        observation: Observation,
        command_reason: str | None,
    ) -> Action:
        rock = _nearest_big_hard_rock(observation)
        if rock is None:
            return self._craft_wait(
                observation,
                "big hard rock not visible",
                command_reason,
            )

        if not _is_adjacent(observation.self.tile, rock.tile):
            approach = _approach_tile_near(observation, rock.tile)
            if approach is None:
                return self._craft_wait(
                    observation,
                    "no walkable tile beside big hard rock",
                    command_reason,
                )
            if observation.self.tile != approach:
                reason = "move beside big hard rock"
                self._annotate(
                    observation,
                    collect_target=rock.tile,
                    reason=reason,
                    collect_reason=reason,
                    collect_target_name=rock.name,
                )
                return Action(ActionType.MOVE_TO, {"x": approach.x, "y": approach.y})

        if not observation.self.is_stationary:
            return self._craft_wait(observation, "wait stationary to knap stone", command_reason)

        reason = "knap stone on big hard rock"
        self._annotate(
            observation,
            collect_target=rock.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=rock.name,
        )
        return Action(
            ActionType.USE,
            {"target_x": rock.tile.x, "target_y": rock.tile.y},
        )

    def _craft_wait(
        self,
        observation: Observation,
        reason: str,
        command_reason: str | None,
    ) -> Action:
        self._annotate(
            observation,
            reason=command_reason or reason,
            collect_reason=reason,
        )
        return Action(ActionType.WAIT, {"ticks": 1})

    def _reset_task_modes(self) -> None:
        self.leader_id = None
        self._current_target = None
        self.collect_requested_by = None
        self.collect_names = frozenset()
        self.collect_stack = None
        self.make_sharp_stone_requested_by = None
        self.stock_camp_requested_by = None
        self.camp_stock = None
        self._stack_source_tile = None
        self._stack_source_set_tick = -10_000
        self._clear_collect_pickup()
        self._clear_collect_drop()

    def _clear_collect(self) -> None:
        self._reset_task_modes()

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
        hands_empty = (
            observation.self.held_object_id is None
            and not observation.self.is_holding_food
            and not observation.self.held_pending
        )
        if hands_empty and elapsed >= 1:
            return None
        remaining = self.config.collect_pickup_retry_cooldown_ticks - elapsed
        if remaining > 0:
            return f"collect pickup retry wait {remaining}"
        return None

    def _maybe_sync_collect_pickup_state(
        self,
        observation: Observation,
        source_tile: Tile,
    ) -> None:
        if observation.self.held_pending:
            return
        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            self._clear_collect_pickup()
            return
        if (
            self._collect_pickup_tile is not None
            and self._collect_pickup_tile != source_tile
            and not _is_adjacent_or_same(observation.self.tile, self._collect_pickup_tile)
        ):
            self._clear_collect_pickup()

    def _decide_collect_pickup(
        self,
        observation: Observation,
        target: ObjectState,
        *,
        reason_prefix: str,
        reason_suffix: str | None = None,
    ) -> Action | None:
        self._maybe_sync_collect_pickup_state(observation, target.tile)

        if not observation.self.is_stationary:
            reason = "wait stationary for pickup"
            self._annotate(
                observation,
                collect_target=target.tile,
                reason=reason,
                collect_reason=reason,
                collect_target_name=target.name,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

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
        if reason_suffix:
            reason = f"{reason_prefix} {target.name} {reason_suffix}"
        else:
            reason = f"{reason_prefix} {target.name}"
        self._annotate(
            observation,
            collect_target=target.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=target.name,
        )
        return Action(ActionType.PICK_UP, {"x": target.tile.x, "y": target.tile.y})

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
        observation.facts["make_sharp_stone_requested_by"] = self.make_sharp_stone_requested_by
        observation.facts["stock_camp_requested_by"] = self.stock_camp_requested_by
        camp = self.camp_stock
        observation.facts["camp_stock"] = (
            {
                "requested_by": camp.requested_by,
                "slots": tuple(
                    {
                        "slot_id": slot.slot_id,
                        "item_name": slot.state.item_name,
                        "desired_count": slot.state.desired_count,
                        "deposited_count": slot.state.deposited_count,
                        "depot_tile": (
                            {"x": slot.state.depot_tile.x, "y": slot.state.depot_tile.y}
                            if slot.state.depot_tile is not None
                            else None
                        ),
                    }
                    for slot in camp.slots
                ),
            }
            if camp is not None
            else None
        )
        stack = self.collect_stack
        observation.facts["collect_stack"] = (
            {
                "requested_by": stack.requested_by,
                "item_name": stack.item_name,
                "desired_count": stack.desired_count,
                "deposited_count": stack.deposited_count,
                "depot_origin": (
                    {"x": stack.depot_origin.x, "y": stack.depot_origin.y}
                    if stack.depot_origin is not None
                    else None
                ),
                "depot_tile": (
                    {"x": stack.depot_tile.x, "y": stack.depot_tile.y}
                    if stack.depot_tile is not None
                    else None
                ),
                "pending_deposit_tile": (
                    {
                        "x": stack.pending_deposit_tile.x,
                        "y": stack.pending_deposit_tile.y,
                    }
                    if stack.pending_deposit_tile is not None
                    else None
                ),
            }
            if stack is not None
            else None
        )


def _chat_events(observation: Observation) -> tuple[Mapping[str, Any], ...]:
    raw = observation.facts.get("chat_events")
    if not isinstance(raw, tuple):
        return ()
    return tuple(event for event in raw if isinstance(event, Mapping))


def _chat_reply(text: str, age: float) -> str | None:
    candidates = _CHAT_REPLY_CANDIDATES.get(text)
    if candidates is None:
        return None
    return fit_say_from_candidates(candidates, age=age)


def _parse_collect_command(text: str) -> str | None:
    prefix = "collect "
    if not text.startswith(prefix):
        return None
    name = text[len(prefix):].strip()
    return name or None


def _parse_collect_stack_command(text: str) -> str | None:
    prefix = "collect stack "
    if not text.startswith(prefix):
        return None
    name = text[len(prefix) :].strip()
    return name or None


def _resolve_stack_rule(observation: Observation, query: str) -> dict[str, Any]:
    normalized = _normalize_name(query)
    catalog = observation.facts.get("stack_collect_catalog")
    if isinstance(catalog, tuple):
        for raw_rule in catalog:
            if not isinstance(raw_rule, dict):
                continue
            aliases = raw_rule.get("query_aliases", ())
            loose_names = raw_rule.get("loose_names", ())
            pile_names = raw_rule.get("pile_names", ())
            if normalized in aliases or normalized in loose_names or normalized in pile_names:
                return raw_rule
    return _fallback_stack_rule(query)


def _fallback_stack_rule(query: str) -> dict[str, Any]:
    normalized = _normalize_name(query)
    display_name = query.strip().title()
    pile_name = f"{normalized} pile"
    return {
        "display_name": display_name,
        "loose_names": (normalized,),
        "pile_names": (pile_name,),
        "loose_object_id": None,
        "pile_object_id": None,
        "depot_target_ids": (),
        "source_target_ids": (),
        "query_aliases": (normalized, pile_name),
    }


def _stack_state_from_rule(
    rule: dict[str, Any],
    *,
    requested_by: int,
    depot_origin: Tile | None,
    depot_tile: Tile | None,
    desired_count: int = 6,
) -> StackCollectState:
    return StackCollectState(
        requested_by=requested_by,
        item_name=str(rule.get("display_name", "item")),
        item_names=frozenset(rule.get("loose_names", ())),
        pile_names=frozenset(rule.get("pile_names", ())),
        depot_origin=depot_origin,
        depot_tile=depot_tile,
        loose_object_id=_optional_int(rule.get("loose_object_id")),
        pile_object_id=_optional_int(rule.get("pile_object_id")),
        depot_target_ids=tuple(rule.get("depot_target_ids", ())),
        source_target_ids=tuple(rule.get("source_target_ids", ())),
        desired_count=desired_count,
        drop_only=bool(rule.get("drop_only", False)),
    )


def _camp_stock_state_from_layout(
    observation: Observation,
    layout: Any,
    *,
    requested_by: int,
) -> CampStockState:
    slots: list[CampSlotProgress] = []
    for slot_spec in layout.slots:
        rule = _resolve_stack_rule(observation, slot_spec.item_query)
        stack_state = _stack_state_from_rule(
            rule,
            requested_by=requested_by,
            depot_origin=None,
            depot_tile=slot_spec.tile,
            desired_count=slot_spec.desired_count,
        )
        slots.append(CampSlotProgress(slot_id=slot_spec.slot_id, state=stack_state))
    return CampStockState(requested_by=requested_by, slots=tuple(slots))


def _camp_stock_complete(camp: CampStockState) -> bool:
    return all(
        slot.state.deposited_count >= slot.state.desired_count for slot in camp.slots
    )


def _camp_stock_deposit_settle_reason(
    policy: MovementFollowPolicy,
    observation: Observation,
    camp: CampStockState,
) -> str | None:
    for slot in camp.slots:
        reason = policy._collect_stack_deposit_settle_reason(observation, slot.state)
        if reason is not None:
            return reason.replace("stack", "stock camp")
    return None


def _camp_slot_for_held_item(
    observation: Observation,
    camp: CampStockState,
) -> CampSlotProgress | None:
    matching: list[CampSlotProgress] = []
    for slot in camp.slots:
        if slot.state.deposited_count >= slot.state.desired_count:
            continue
        if slot.state.depot_tile is None:
            continue
        if _is_holding_collect_target(observation, slot.state.item_names):
            matching.append(slot)
    if not matching:
        return None
    return min(
        matching,
        key=lambda slot: observation.self.tile.distance_to(slot.state.depot_tile),
    )


def _select_camp_work(
    observation: Observation,
    camp: CampStockState,
    policy: MovementFollowPolicy,
) -> tuple[ObjectState, CampSlotProgress] | None:
    best: tuple[int, ObjectState, CampSlotProgress] | None = None
    for slot in camp.slots:
        if slot.state.deposited_count >= slot.state.desired_count:
            continue
        source = _nearest_stack_source(observation, slot.state)
        if source is None:
            continue
        distance = observation.self.tile.distance_to(source.tile)
        if best is None or distance < best[0]:
            best = (distance, source, slot)
    if best is None:
        return None
    policy._stack_source_tile = best[1].tile
    policy._stack_source_set_tick = observation.tick
    return best[1], best[2]


def _decide_stack_deposit_action(
    observation: Observation,
    state: StackCollectState,
    depot: Tile,
    depot_object: ObjectState | None,
    policy: MovementFollowPolicy,
    *,
    slot_id: int | None = None,
) -> tuple[Action, str] | None:
    drop_only = state.drop_only
    slot_prefix = f"camp slot {slot_id} " if slot_id is not None else ""
    progress = f"{state.deposited_count + 1}/{state.desired_count}"

    if depot_object is None:
        policy._note_stack_deposit_attempt(observation, state, depot)
        reason = f"{slot_prefix}start {state.item_name} stack {progress}"
        return (
            Action(ActionType.DROP, {"x": depot.x, "y": depot.y}),
            reason,
        )

    if not _is_stack_depot_object(depot_object, state):
        return None

    policy._note_stack_deposit_attempt(observation, state, depot)
    if drop_only:
        reason = f"{slot_prefix}add {state.item_name} {progress}"
        return (
            Action(ActionType.DROP, {"x": depot.x, "y": depot.y}),
            reason,
        )

    reason = f"{slot_prefix}add {state.item_name} to stack {progress}"
    return (
        Action(
            ActionType.USE,
            {
                "target_x": depot.x,
                "target_y": depot.y,
                "expect_empty_hands": True,
            },
        ),
        reason,
    )


def _player_by_id(observation: Observation, player_id: int) -> PlayerState | None:
    for player in observation.nearby_players:
        if player.player_id == player_id:
            return player
    return None


def _speaker_tile(observation: Observation, player_id: int) -> Tile | None:
    speaker = _player_by_id(observation, player_id)
    if speaker is not None:
        return speaker.tile
    for event in reversed(_chat_events(observation)):
        if event.get("player_id") != player_id:
            continue
        raw = event.get("speaker_tile")
        if isinstance(raw, dict) and "x" in raw and "y" in raw:
            return Tile(int(raw["x"]), int(raw["y"]))
        break
    return None


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


def _nearest_stack_source(
    observation: Observation,
    state: StackCollectState,
) -> ObjectState | None:
    danger = _tile_set(observation.facts.get("avoid_targets"))
    danger.update(
        _tile_set(observation.facts.get("danger_tiles")),
    )
    candidates: list[ObjectState] = []
    for obj in observation.nearby_objects:
        if obj.tile == state.depot_tile:
            continue
        if obj.tile in danger:
            continue
        if _normalize_name(obj.name) in state.item_names:
            candidates.append(obj)
        elif _is_stack_pile_source(obj, state):
            candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: observation.self.tile.distance_to(obj.tile))


def _select_stack_source(
    observation: Observation,
    state: StackCollectState,
    policy: MovementFollowPolicy,
) -> ObjectState | None:
    danger = _tile_set(observation.facts.get("avoid_targets"))
    danger.update(_tile_set(observation.facts.get("danger_tiles")))
    now_tick = observation.tick
    if (
        policy._stack_source_tile is not None
        and now_tick - policy._stack_source_set_tick
        < policy.config.stack_source_retarget_cooldown_ticks
    ):
        for obj in observation.nearby_objects:
            if obj.tile == policy._stack_source_tile and obj.tile not in danger:
                if obj.tile == state.depot_tile:
                    continue
                if _normalize_name(obj.name) in state.item_names or _is_stack_pile_source(
                    obj, state
                ):
                    return obj

    selected = _nearest_stack_source(observation, state)
    if selected is not None:
        policy._stack_source_tile = selected.tile
        policy._stack_source_set_tick = now_tick
    else:
        policy._stack_source_tile = None
    return selected


def _is_stack_pile_source(
    obj: ObjectState,
    state: StackCollectState,
) -> bool:
    if state.pile_object_id is not None and obj.object_id == state.pile_object_id:
        return True
    if obj.object_id in state.source_target_ids:
        return True
    name = _normalize_name(obj.name)
    if name in state.pile_names or _name_is_item_pile(name, state):
        return True
    return False


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


def _select_stack_depot_tile(
    observation: Observation,
    origin: Tile,
    state: StackCollectState,
) -> Tile | None:
    blocked = _tile_set(observation.facts.get("blocked_tiles"))
    blocked.update(_tile_set(observation.facts.get("known_blocking_tiles")))
    blocked.update(_tile_set(observation.facts.get("avoid_targets")))
    blocked.update(_tile_set(observation.facts.get("danger_tiles")))
    occupied_by_players = {player.tile for player in observation.nearby_players}
    candidates = _drop_candidates(origin)
    for tile in candidates:
        if tile in blocked or tile in occupied_by_players:
            continue
        obj = _object_at_tile(observation, tile)
        if obj is None or _is_stack_depot_object(obj, state):
            return tile
    return None


def _object_at_tile(observation: Observation, tile: Tile) -> ObjectState | None:
    for obj in observation.nearby_objects:
        if obj.tile == tile:
            return obj
    return None


def _is_stack_depot_object(
    obj: ObjectState,
    state: StackCollectState,
) -> bool:
    if state.loose_object_id is not None and obj.object_id == state.loose_object_id:
        return True
    if state.pile_object_id is not None and obj.object_id == state.pile_object_id:
        return True
    if obj.object_id in state.depot_target_ids:
        return True
    name = _normalize_name(obj.name)
    if name in state.item_names or name in state.pile_names:
        return True
    if _name_is_item_pile(name, state):
        return True
    # Server-generated stack states may use ids missing from local game_data.
    if name.startswith("unknown:"):
        return True
    return False


def _name_is_item_pile(name: str, state: StackCollectState) -> bool:
    for base in state.item_names:
        if name == f"{base} pile":
            return True
        if base in name and "pile" in name:
            return True
    return False


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


def _is_loose_stone_name(name: str) -> bool:
    return _normalize_name(name) == "stone"


def _is_big_hard_rock_name(name: str) -> bool:
    return _normalize_name(name) == "big hard rock"


def _is_sharp_stone_name(name: str) -> bool:
    return _normalize_name(name) == "sharp stone"


def _is_holding_loose_stone(observation: Observation) -> bool:
    if observation.self.held_object_id == 33:
        return True
    held_name = observation.self.held_object_name
    return held_name is not None and _is_loose_stone_name(held_name)


def _is_holding_sharp_stone(observation: Observation) -> bool:
    if observation.self.held_object_id == 34:
        return True
    held_name = observation.self.held_object_name
    return held_name is not None and _is_sharp_stone_name(held_name)


def _nearest_loose_stone(observation: Observation) -> ObjectState | None:
    candidates = [
        obj for obj in observation.nearby_objects if _is_loose_stone_name(obj.name)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda obj: observation.self.tile.distance_to(obj.tile),
    )


def _nearest_big_hard_rock(observation: Observation) -> ObjectState | None:
    candidates = [
        obj for obj in observation.nearby_objects if _is_big_hard_rock_name(obj.name)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda obj: observation.self.tile.distance_to(obj.tile),
    )


def _approach_tile_near(observation: Observation, target: Tile) -> Tile | None:
    blocked = _tile_set(observation.facts.get("blocked_tiles"))
    blocked.update(_tile_set(observation.facts.get("known_blocking_tiles")))
    occupied = {player.tile for player in observation.nearby_players}
    best: Tile | None = None
    best_distance: int | None = None
    for candidate in _drop_candidates(target):
        if candidate == target:
            continue
        if candidate in blocked or candidate in occupied:
            continue
        distance = observation.self.tile.distance_to(candidate)
        if best is None or distance < best_distance:
            best = candidate
            best_distance = distance
    return best


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


def _is_adjacent_or_same(a: Tile, b: Tile) -> bool:
    return max(abs(a.x - b.x), abs(a.y - b.y)) <= 1
