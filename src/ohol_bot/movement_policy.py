from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping

from .follow_target import select_follow_target
from .movement_chat import consume_chat_commands, optional_int, parse_collect_stack_command, player_by_id, speaker_tile
from .movement_facts import annotate_movement_facts
from .stack_collect import (
    CampSlotProgress,
    CampStockState,
    StackCollectState,
    camp_slot_for_held_item,
    camp_slot_needing_harvest,
    camp_stock_complete,
    camp_stock_deposit_settle_reason,
    camp_stock_state_from_layout,
    decide_stack_deposit_action,
    harvest_work_available,
    holding_harvest_product,
    holding_harvest_tool,
    harvest_work_tile_valid,
    is_holding_collect_target,
    is_stack_depot_object,
    is_stack_loose_source,
    is_stack_pile_source,
    nearest_harvest_dug,
    nearest_harvest_plant,
    nearest_loose_harvest_tool,
    nearest_loose_sharp_stone,
    nearest_stack_source,
    object_matches_harvest_dug,
    object_matches_harvest_plant,
    resolve_stack_rule,
    select_camp_work,
    select_stack_depot_tile,
    select_stack_source,
    is_holding_surplus_camp_item,
    stack_state_from_rule,
    _should_prefer_loose_over_harvest,
)

from .interact_flow import (
    approach_tile_orthogonal,
    can_interact_with_tile,
    decide_navigate_or_pickup,
    decide_navigate_to_interact,
    decide_pickup_action,
    ensure_empty_hands,
    maybe_sync_pickup_state,
    select_drop_tile,
)
from .action_pending import PendingAction
from .harvest import build_harvest_catalog, merge_harvest_into_stack_rule
from .camp_depot import camp_layout_from_facts
from .model import Action, ActionType, ObjectState, Observation, PlayerState, Tile
from .danger import base_object_name
from .home import DEFAULT_HOME_AREA_RADIUS, find_home_center_near
from .policy import Policy
from .speech import fit_say_from_candidates, fit_say_text
from .object_names import (
    is_big_hard_rock_name,
    is_loose_stone_name,
    is_sharp_stone_name,
    normalize_item_name,
)
from .spatial_queries import nearest_object, object_at_tile
from .tiles import (
    chebyshev,
    danger_tiles,
    is_orthogonally_adjacent,
)


@dataclass(frozen=True, slots=True)
class FollowConfig:
    desired_distance: int = 1
    retarget_cooldown_ticks: int = 4
    collect_pickup_retry_cooldown_ticks: int = 3
    collect_drop_retry_cooldown_ticks: int = 12
    collect_drop_settle_ticks: int = 3
    collect_stack_deposit_settle_ticks: int = 3
    stack_source_retarget_cooldown_ticks: int = 6
    knap_settle_ticks: int = 6


_CHAT_REPLY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "hello": ("HELLO", "HI", "H"),
    "hi": ("HI", "H"),
    "hey": ("HELLO", "HI", "H"),
}


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
        self._pickup_pending = PendingAction()
        self._drop_pending = PendingAction()
        self.collect_stack: StackCollectState | None = None
        self._stack_source_tile: Tile | None = None
        self._stack_source_set_tick = -10_000
        self._harvest_work_tile: Tile | None = None
        self._knap_pending = PendingAction()
        self.make_sharp_stone_requested_by: int | None = None
        self.stock_camp_requested_by: int | None = None
        self.camp_stock: CampStockState | None = None
        self._camp_ignored_pickup_until: dict[Tile, int] = {}
        self._pending_say: str | None = None

    def decide(self, observation: Observation) -> Action:
        command_reason = consume_chat_commands(self, observation)
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

        distance = chebyshev(observation.self.tile, leader.tile)
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
        return consume_chat_commands(self, observation)

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

        if state.harvest_rule is not None and harvest_work_available(
            observation,
            state.harvest_rule,
            state.depot_tile,
        ) and not _should_prefer_loose_over_harvest(observation, state, self):
            harvest_action = self._decide_harvest_step(
                observation,
                state,
                command_reason,
            )
            if harvest_action is not None:
                return harvest_action

        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            if is_holding_collect_target(observation, state.item_names):
                if not can_interact_with_tile(observation.self.tile, depot):
                    move_action, move_reason = decide_navigate_to_interact(
                        observation,
                        depot,
                        target_name=state.item_name,
                        reason_prefix="return to stack depot with",
                    )
                    self._annotate(
                        observation,
                        collect_target=depot,
                        reason=move_reason,
                        collect_reason=move_reason,
                        collect_target_name=state.item_name,
                    )
                    return move_action

                depot_object = object_at_tile(observation, depot)
                deposit_action, deposit_reason = decide_stack_deposit_action(
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

            drop_tile = select_drop_tile(observation)
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

        target = select_stack_source(observation, state, self)
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

        return self._decide_navigate_or_pickup(
            observation,
            target,
            reason_prefix="pick up",
            reason_suffix="for stack",
        )

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

        if camp_stock_complete(camp):
            hands_empty = (
                observation.self.held_object_id is None
                and not observation.self.is_holding_food
            )
            if (
                hands_empty
                and not observation.self.held_pending
                and camp_stock_deposit_settle_reason(self, observation, camp) is None
            ):
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

        settle_reason = camp_stock_deposit_settle_reason(self, observation, camp)
        if settle_reason is not None:
            self._annotate(
                observation,
                reason=settle_reason,
                collect_reason=settle_reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        active_harvest_slot = camp_slot_needing_harvest(observation, camp)
        if active_harvest_slot is not None and _should_prefer_loose_over_harvest(
            observation,
            active_harvest_slot.state,
            self,
        ):
            active_harvest_slot = None
        if active_harvest_slot is not None:
            harvest_action = self._decide_harvest_step(
                observation,
                active_harvest_slot.state,
                command_reason,
            )
            if harvest_action is not None:
                return harvest_action

        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            active_slot = camp_slot_for_held_item(observation, camp)
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
                if not can_interact_with_tile(observation.self.tile, depot):
                    move_action, move_reason = decide_navigate_to_interact(
                        observation,
                        depot,
                        target_name=active_slot.state.item_name,
                        reason_prefix=(
                            f"return to camp slot {active_slot.slot_id} with"
                        ),
                    )
                    self._annotate(
                        observation,
                        collect_target=depot,
                        reason=move_reason,
                        collect_reason=move_reason,
                        collect_target_name=active_slot.state.item_name,
                    )
                    return move_action

                depot_object = object_at_tile(observation, depot)
                deposit_action, deposit_reason = decide_stack_deposit_action(
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

            if is_holding_surplus_camp_item(observation, camp):
                drop_tile = select_drop_tile(observation)
                if drop_tile is None:
                    reason = (
                        f"stock camp cannot drop surplus "
                        f"{observation.self.held_object_name or 'object'}"
                    )
                    self._annotate(
                        observation,
                        reason=reason,
                        collect_reason=reason,
                    )
                    return Action(ActionType.WAIT, {"ticks": 1})
                self._note_collect_drop_attempt(observation, drop_tile)
                self._note_camp_surplus_ignored(observation, camp)
                held_name = observation.self.held_object_name or "object"
                reason = f"drop surplus {held_name}"
                self._annotate(
                    observation,
                    reason=reason,
                    collect_reason=reason,
                )
                return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

            drop_tile = select_drop_tile(observation)
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

        work = select_camp_work(observation, camp, self)
        if work is None:
            reason = command_reason or "stock camp waiting: no visible camp items"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        _source, active_slot = work
        target = select_stack_source(observation, active_slot.state, self)
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

        return self._decide_navigate_or_pickup(
            observation,
            target,
            reason_prefix="pick up",
            reason_suffix=f"for camp slot {active_slot.slot_id}",
        )

    def _maybe_note_stack_deposit_complete(
        self,
        observation: Observation,
        state: StackCollectState,
    ) -> bool:
        if state.deposit_pending.tile is None:
            return False
        elapsed = observation.tick - state.deposit_pending.sent_tick
        if elapsed < self.config.collect_stack_deposit_settle_ticks:
            return False
        if observation.self.held_pending:
            return False
        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            return False
        state.deposited_count += 1
        state.deposit_pending.clear()
        return True

    def _collect_stack_deposit_settle_reason(
        self,
        observation: Observation,
        state: StackCollectState,
    ) -> str | None:
        return state.deposit_pending.settle_reason(
            observation.tick,
            self.config.collect_stack_deposit_settle_ticks,
            "stack deposit",
        )

    def _note_stack_deposit_attempt(
        self,
        observation: Observation,
        state: StackCollectState,
        tile: Tile,
    ) -> None:
        state.deposit_pending.note_attempt(observation.tick, tile)

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
            if is_holding_collect_target(observation, self.collect_names):
                reason = f"collect complete holding {held_name}"
                self._clear_collect()
                self.mode = "idle"
                self._annotate(
                    observation,
                    reason=reason,
                    collect_reason=reason,
                )
                return Action(ActionType.WAIT, {"ticks": 1})

        drop_action, drop_reason = ensure_empty_hands(
            observation,
            held_name=held_name,
            drop_settle_reason=self._collect_drop_settle_reason,
            drop_retry_reason=self._collect_drop_retry_reason,
            note_drop_attempt=self._note_collect_drop_attempt,
            clear_drop_state=self._clear_collect_drop,
            reason_prefix="drop held",
            reason_suffix="before collect",
        )
        if drop_action is not None:
            self._annotate(
                observation,
                reason=drop_reason or "collect drop pending",
                collect_reason=drop_reason or "collect drop pending",
            )
            return drop_action

        target = nearest_object(observation, names=self.collect_names)
        if target is None:
            self._annotate(
                observation,
                reason=command_reason or "collect target not visible",
                collect_reason=command_reason or "collect target not visible",
            )
            return Action(ActionType.WAIT, {"ticks": 1})

        action, reason = decide_navigate_or_pickup(
            observation,
            target,
            pending=self._pickup_pending,
            pickup_retry_reason=self._collect_pickup_retry_reason,
            note_pickup_attempt=self._note_collect_pickup_attempt,
            clear_pickup=self._clear_collect_pickup,
            reason_prefix="pick up",
        )
        self._annotate(
            observation,
            collect_target=target.tile,
            reason=command_reason or reason,
            collect_reason=reason,
            collect_target_name=target.name,
        )
        return action

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
            drop_tile = select_drop_tile(observation)
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

        return self._decide_navigate_or_pickup(
            observation,
            stone,
            reason_prefix="pick up",
        )

    def _decide_navigate_or_pickup(
        self,
        observation: Observation,
        target: ObjectState,
        *,
        reason_prefix: str,
        reason_suffix: str | None = None,
    ) -> Action:
        action, reason = decide_navigate_or_pickup(
            observation,
            target,
            pending=self._pickup_pending,
            pickup_retry_reason=self._collect_pickup_retry_reason,
            note_pickup_attempt=self._note_collect_pickup_attempt,
            clear_pickup=self._clear_collect_pickup,
            reason_prefix=reason_prefix,
            reason_suffix=reason_suffix,
        )
        self._annotate(
            observation,
            collect_target=target.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=target.name,
        )
        return action

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

        if not is_orthogonally_adjacent(observation.self.tile, rock.tile):
            approach = approach_tile_orthogonal(observation, rock.tile)
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

        knap_wait = self._knap_settle_reason(observation)
        if knap_wait is not None:
            return self._craft_wait(observation, knap_wait, command_reason)

        if self._knap_pending.tile is not None:
            self._clear_knap_attempt()

        self._note_knap_attempt(observation, rock.tile)
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

    def _note_knap_attempt(self, observation: Observation, rock_tile: Tile) -> None:
        self._knap_pending.note_attempt(observation.tick, rock_tile)

    def _clear_knap_attempt(self) -> None:
        self._knap_pending.clear()

    def _knap_settle_reason(self, observation: Observation) -> str | None:
        if self._knap_pending.tile is None:
            return None
        if _is_holding_sharp_stone(observation):
            self._clear_knap_attempt()
            return None
        if not _is_holding_loose_stone(observation):
            self._clear_knap_attempt()
            return None
        return self._knap_pending.settle_reason(
            observation.tick,
            self.config.knap_settle_ticks,
            "knap",
        )

    def _decide_harvest_step(
        self,
        observation: Observation,
        state: StackCollectState,
        command_reason: str | None,
    ) -> Action | None:
        rule = state.harvest_rule
        if rule is None:
            return None

        if holding_harvest_product(observation, rule):
            return None

        if observation.self.held_pending:
            return self._craft_wait(observation, "harvest action pending", command_reason)

        knap_wait = self._knap_settle_reason(observation)
        if knap_wait is not None:
            return self._craft_wait(observation, knap_wait, command_reason)

        plant = nearest_harvest_plant(observation, rule, state.depot_tile)
        dug_target = nearest_harvest_dug(observation, rule, state.depot_tile)
        if plant is not None:
            self._harvest_work_tile = plant.tile
        elif dug_target is not None:
            self._harvest_work_tile = dug_target.tile
        work_tile = self._harvest_work_tile
        if work_tile is not None and not harvest_work_tile_valid(
            observation,
            work_tile,
            rule,
        ):
            self._harvest_work_tile = None
            work_tile = None

        if plant is None and dug_target is None:
            return None

        if observation.self.held_object_id is not None or observation.self.is_holding_food:
            if _is_holding_loose_stone(observation):
                knap_action = self._decide_acquire_sharp_stone_step(
                    observation,
                    command_reason,
                )
                if knap_action is not None:
                    return knap_action

            if holding_harvest_tool(observation, rule) or _is_holding_sharp_stone(
                observation
            ):
                dug = (
                    object_at_tile(observation, work_tile)
                    if work_tile is not None
                    else None
                )
                if dug is not None and object_matches_harvest_dug(dug, rule):
                    drop_tile = select_drop_tile(observation)
                    if drop_tile is None:
                        self._craft_wait(
                            observation,
                            "harvest cannot drop tool",
                            command_reason,
                        )
                        return Action(ActionType.WAIT, {"ticks": 1})
                    self._note_collect_drop_attempt(observation, drop_tile)
                    reason = "drop harvest tool before gathering"
                    self._annotate(
                        observation,
                        reason=reason,
                        collect_reason=reason,
                    )
                    return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

                if plant is None:
                    return None

                if not is_orthogonally_adjacent(observation.self.tile, plant.tile):
                    approach = approach_tile_orthogonal(observation, plant.tile)
                    if approach is None:
                        self._craft_wait(
                            observation,
                            f"no walkable tile beside {plant.name}",
                            command_reason,
                        )
                        return Action(ActionType.WAIT, {"ticks": 1})
                    if observation.self.tile != approach:
                        reason = command_reason or f"move beside {plant.name} to dig"
                        self._annotate(
                            observation,
                            collect_target=plant.tile,
                            reason=reason,
                            collect_reason=reason,
                            collect_target_name=plant.name,
                        )
                        return Action(ActionType.MOVE_TO, {"x": approach.x, "y": approach.y})

                if not observation.self.is_stationary:
                    self._craft_wait(
                        observation,
                        "wait stationary to dig plant",
                        command_reason,
                    )
                    return Action(ActionType.WAIT, {"ticks": 1})

                reason = f"dig {plant.name} with harvest tool"
                self._annotate(
                    observation,
                    collect_target=plant.tile,
                    reason=reason,
                    collect_reason=reason,
                    collect_target_name=plant.name,
                )
                return Action(
                    ActionType.USE,
                    {"target_x": plant.tile.x, "target_y": plant.tile.y},
                )

            drop_tile = select_drop_tile(observation)
            if drop_tile is None:
                self._craft_wait(
                    observation,
                    f"harvest cannot drop held {observation.self.held_object_name or 'object'}",
                    command_reason,
                )
                return Action(ActionType.WAIT, {"ticks": 1})
            self._note_collect_drop_attempt(observation, drop_tile)
            held_name = observation.self.held_object_name or "object"
            reason = f"drop held {held_name} before harvest"
            self._annotate(
                observation,
                reason=reason,
                collect_reason=reason,
            )
            return Action(ActionType.DROP, {"x": drop_tile.x, "y": drop_tile.y})

        settle_reason = self._collect_drop_settle_reason(observation)
        if settle_reason is not None:
            return self._craft_wait(observation, settle_reason, command_reason)
        self._clear_collect_drop()

        if work_tile is not None:
            dug = object_at_tile(observation, work_tile)
            if dug is not None and object_matches_harvest_dug(dug, rule):
                if not is_orthogonally_adjacent(observation.self.tile, work_tile):
                    approach = approach_tile_orthogonal(observation, work_tile)
                    if approach is None:
                        self._craft_wait(
                            observation,
                            f"no walkable tile beside {dug.name}",
                            command_reason,
                        )
                        return Action(ActionType.WAIT, {"ticks": 1})
                    if observation.self.tile != approach:
                        reason = command_reason or f"move beside {dug.name} to gather"
                        self._annotate(
                            observation,
                            collect_target=work_tile,
                            reason=reason,
                            collect_reason=reason,
                            collect_target_name=dug.name,
                        )
                        return Action(ActionType.MOVE_TO, {"x": approach.x, "y": approach.y})

                if not observation.self.is_stationary:
                    self._craft_wait(
                        observation,
                        "wait stationary to gather harvest",
                        command_reason,
                    )
                    return Action(ActionType.WAIT, {"ticks": 1})

                reason = f"gather {state.item_name} from dug plant"
                self._annotate(
                    observation,
                    collect_target=work_tile,
                    reason=reason,
                    collect_reason=reason,
                    collect_target_name=dug.name,
                )
                return Action(
                    ActionType.USE,
                    {"target_x": work_tile.x, "target_y": work_tile.y},
                )

        if _is_holding_sharp_stone(observation) or _is_holding_loose_stone(observation):
            knap_action = self._decide_acquire_sharp_stone_step(
                observation,
                command_reason,
            )
            if knap_action is not None:
                return knap_action

        tool = nearest_loose_harvest_tool(observation, rule)
        if tool is not None:
            return self._decide_navigate_or_pickup(
                observation,
                tool,
                reason_prefix="pick up",
                reason_suffix="for harvest",
            )

        knap_action = self._decide_acquire_sharp_stone_step(observation, command_reason)
        if knap_action is not None:
            return knap_action

        if plant is not None:
            move_action, move_reason = decide_navigate_to_interact(
                observation,
                plant.tile,
                target_name=plant.name,
                reason_prefix="move beside",
            )
            self._annotate(
                observation,
                collect_target=plant.tile,
                reason=move_reason,
                collect_reason=move_reason,
                collect_target_name=plant.name,
            )
            return move_action

        return None

    def _decide_acquire_sharp_stone_step(
        self,
        observation: Observation,
        command_reason: str | None,
    ) -> Action | None:
        if _is_holding_sharp_stone(observation):
            return None

        if _is_holding_loose_stone(observation):
            return self._decide_make_sharp_stone_on_rock(observation, command_reason)

        sharp = nearest_loose_sharp_stone(observation)
        if sharp is not None:
            return self._decide_navigate_or_pickup(
                observation,
                sharp,
                reason_prefix="pick up",
                reason_suffix="for harvest",
            )

        stone = _nearest_loose_stone(observation)
        if stone is None:
            return None

        return self._decide_navigate_or_pickup(
            observation,
            stone,
            reason_prefix="pick up",
            reason_suffix="to knap",
        )

    def _reset_task_modes(self) -> None:
        self.leader_id = None
        self._current_target = None
        self.collect_requested_by = None
        self.collect_names = frozenset()
        self.collect_stack = None
        self.make_sharp_stone_requested_by = None
        self.stock_camp_requested_by = None
        self.camp_stock = None
        self._camp_ignored_pickup_until = {}
        self._harvest_work_tile = None
        self._clear_knap_attempt()
        self._stack_source_tile = None
        self._stack_source_set_tick = -10_000
        self._clear_collect_pickup()
        self._clear_collect_drop()

    def _clear_collect(self) -> None:
        self._reset_task_modes()

    def _clear_collect_pickup(self) -> None:
        self._pickup_pending.clear()

    def _clear_collect_drop(self) -> None:
        self._drop_pending.clear()

    def _camp_pickup_ignored(self, observation: Observation, tile: Tile) -> bool:
        until_tick = self._camp_ignored_pickup_until.get(tile)
        if until_tick is None:
            return False
        if observation.tick >= until_tick:
            del self._camp_ignored_pickup_until[tile]
            return False
        return True

    def _note_camp_surplus_ignored(
        self,
        observation: Observation,
        camp: CampStockState,
    ) -> None:
        until_tick = observation.tick + 40
        for obj in observation.nearby_objects:
            for slot in camp.slots:
                if is_stack_loose_source(obj, slot.state):
                    self._camp_ignored_pickup_until[obj.tile] = until_tick

    def _collect_drop_retry_reason(
        self,
        observation: Observation,
        tile: Tile,
    ) -> str | None:
        return self._drop_pending.retry_reason(
            observation.tick,
            self.config.collect_drop_retry_cooldown_ticks,
            "collect drop",
            tile=tile,
        )

    def _collect_drop_settle_reason(self, observation: Observation) -> str | None:
        return self._drop_pending.settle_reason(
            observation.tick,
            self.config.collect_drop_settle_ticks,
            "collect drop",
        )

    def _note_collect_drop_attempt(
        self,
        observation: Observation,
        tile: Tile,
    ) -> None:
        self._drop_pending.note_attempt(observation.tick, tile)

    def _collect_pickup_retry_reason(
        self,
        observation: Observation,
        tile: Tile,
    ) -> str | None:
        if self._pickup_pending.tile != tile:
            return None
        elapsed = observation.tick - self._pickup_pending.sent_tick
        hands_empty = (
            observation.self.held_object_id is None
            and not observation.self.is_holding_food
            and not observation.self.held_pending
        )
        if hands_empty and elapsed >= 1:
            return None
        return self._pickup_pending.retry_reason(
            observation.tick,
            self.config.collect_pickup_retry_cooldown_ticks,
            "collect pickup",
            tile=tile,
        )

    def _decide_collect_pickup(
        self,
        observation: Observation,
        target: ObjectState,
        *,
        reason_prefix: str,
        reason_suffix: str | None = None,
    ) -> Action | None:
        maybe_sync_pickup_state(
            observation,
            target.tile,
            pending=self._pickup_pending,
            clear_pickup=self._clear_collect_pickup,
        )
        action, reason = decide_pickup_action(
            observation,
            target,
            pending=self._pickup_pending,
            pickup_retry_reason=self._collect_pickup_retry_reason,
            note_pickup_attempt=self._note_collect_pickup_attempt,
            reason_prefix=reason_prefix,
            reason_suffix=reason_suffix,
        )
        self._annotate(
            observation,
            collect_target=target.tile,
            reason=reason,
            collect_reason=reason,
            collect_target_name=target.name,
        )
        return action

    def _note_collect_pickup_attempt(
        self,
        observation: Observation,
        tile: Tile,
    ) -> None:
        self._pickup_pending.note_attempt(observation.tick, tile)

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
        return select_follow_target(self, observation, leader)


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
                        "x": stack.deposit_pending.tile.x,
                        "y": stack.deposit_pending.tile.y,
                    }
                    if stack.deposit_pending.tile is not None
                    else None
                ),
            }
            if stack is not None
            else None
        )



def _is_holding_loose_stone(observation: Observation) -> bool:
    if observation.self.held_object_id == 33:
        return True
    held_name = observation.self.held_object_name
    return held_name is not None and is_loose_stone_name(held_name)


def _is_holding_sharp_stone(observation: Observation) -> bool:
    if observation.self.held_object_id == 34:
        return True
    held_name = observation.self.held_object_name
    return held_name is not None and is_sharp_stone_name(held_name)


def _nearest_loose_stone(observation: Observation) -> ObjectState | None:
    return nearest_object(
        observation,
        predicate=lambda obj: is_loose_stone_name(obj.name),
        skip_danger=False,
    )


def _nearest_big_hard_rock(observation: Observation) -> ObjectState | None:
    return nearest_object(
        observation,
        predicate=lambda obj: is_big_hard_rock_name(obj.name),
        skip_danger=False,
    )


from .stack_collect import (  # noqa: E402 — test/backward-compat re-exports
    _camp_stock_state_from_layout,
    _nearest_harvest_plant,
    _nearest_stack_source,
    _should_prefer_loose_over_harvest,
)
from .movement_chat import parse_collect_stack_command as _parse_collect_stack_command  # noqa: E402
