from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from .camp_depot import camp_layout_from_facts
from .danger import base_object_name
from .home import DEFAULT_HOME_AREA_RADIUS, find_home_center_near
from .model import Observation, PlayerState, Tile
from .speech import fit_say_from_candidates

if TYPE_CHECKING:
    from .movement_policy import MovementFollowPolicy

_CHAT_REPLY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "hello": ("HELLO", "HI", "H"),
    "hi": ("HI", "H"),
    "hey": ("HELLO", "HI", "H"),
}


def chat_events(observation: Observation) -> tuple[Mapping[str, Any], ...]:
    raw = observation.facts.get("chat_events")
    if not isinstance(raw, tuple):
        return ()
    return tuple(event for event in raw if isinstance(event, Mapping))


def chat_reply(text: str, age: float) -> str | None:
    candidates = _CHAT_REPLY_CANDIDATES.get(text)
    if candidates is None:
        return None
    return fit_say_from_candidates(candidates, age=age)


def parse_collect_command(text: str) -> str | None:
    prefix = "collect "
    if not text.startswith(prefix):
        return None
    name = text[len(prefix) :].strip()
    return name or None


def parse_collect_stack_command(text: str) -> str | None:
    prefix = "collect stack "
    if not text.startswith(prefix):
        return None
    name = text[len(prefix) :].strip()
    return name or None


def player_by_id(observation: Observation, player_id: int) -> PlayerState | None:
    for player in observation.nearby_players:
        if player.player_id == player_id:
            return player
    return None


def speaker_tile(observation: Observation, player_id: int) -> Tile | None:
    speaker = player_by_id(observation, player_id)
    if speaker is not None:
        return speaker.tile
    for event in reversed(chat_events(observation)):
        if event.get("player_id") != player_id:
            continue
        raw = event.get("speaker_tile")
        if isinstance(raw, dict) and "x" in raw and "y" in raw:
            return Tile(int(raw["x"]), int(raw["y"]))
        break
    return None


def optional_int(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def consume_chat_commands(
    policy: MovementFollowPolicy,
    observation: Observation,
) -> str | None:
    from .stack_collect import (
        camp_stock_state_from_layout,
        resolve_stack_rule,
        select_stack_depot_tile,
        stack_state_from_rule,
    )

    reason = None
    for event in chat_events(observation):
        sequence = int(event.get("sequence", 0))
        if sequence <= policy._last_chat_sequence:
            continue
        policy._last_chat_sequence = sequence
        player_id = optional_int(event.get("player_id"))
        text = str(event.get("text", "")).strip().lower()
        if player_id is None or player_id == observation.self.player_id:
            continue
        if text == "follow":
            policy._reset_task_modes()
            policy.mode = "follow"
            policy.leader_id = player_id
            policy._current_target = None
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
                policy.leader_id is None
                or policy.leader_id == player_id
                or policy.make_sharp_stone_requested_by == player_id
                or policy.collect_requested_by == player_id
                or policy.stock_camp_requested_by == player_id
            ):
                policy.mode = "idle"
                policy.leader_id = None
                policy._current_target = None
                policy._clear_collect()
                reason = f"stop command from player {player_id}"
        elif text == "stock camp":
            layout = camp_layout_from_facts(observation.facts.get("camp_layout"))
            if layout is None and observation.home is not None:
                from .camp_depot import build_camp_layout

                layout = build_camp_layout(observation.home)
            if layout is None:
                reason = f"stock camp rejected: home not set (player {player_id})"
            else:
                policy._reset_task_modes()
                policy.mode = "stock_camp"
                policy.stock_camp_requested_by = player_id
                policy.camp_stock = camp_stock_state_from_layout(
                    observation,
                    layout,
                    requested_by=player_id,
                )
                reason = f"stock camp from player {player_id}"
        elif text == "make sharp stone":
            policy._reset_task_modes()
            policy.mode = "make_sharp_stone"
            policy.make_sharp_stone_requested_by = player_id
            reason = f"make sharp stone from player {player_id}"
        elif text == "set home here":
            speaker = speaker_tile(observation, player_id)
            if speaker is not None:
                center = find_home_center_near(observation, speaker)
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
                        "x": speaker.x,
                        "y": speaker.y,
                    }
                    observation.facts["set_home_radius"] = DEFAULT_HOME_AREA_RADIUS
                    reason = (
                        f"set home from player {player_id} at "
                        f"({speaker.x}, {speaker.y}); no well/spring nearby"
                    )
        elif (reply := chat_reply(text, observation.self.age)) is not None:
            policy._pending_say = reply
            reason = f"chat greeting from player {player_id}"
        else:
            stack_item = parse_collect_stack_command(text)
            if stack_item is not None:
                policy._reset_task_modes()
                policy.mode = "collect_stack"
                speaker = player_by_id(observation, player_id)
                depot_origin = speaker.tile if speaker is not None else None
                stack_rule = resolve_stack_rule(observation, stack_item)
                depot_tile = (
                    select_stack_depot_tile(observation, depot_origin, stack_rule)
                    if depot_origin is not None
                    else None
                )
                policy.collect_stack = stack_state_from_rule(
                    stack_rule,
                    requested_by=player_id,
                    depot_origin=depot_origin,
                    depot_tile=depot_tile,
                )
                reason = f"collect stack command from player {player_id}"
                continue
            collect_name = parse_collect_command(text)
            if collect_name is not None:
                policy._reset_task_modes()
                policy.mode = "collect"
                policy._clear_collect_pickup()
                policy.collect_requested_by = player_id
                policy.collect_names = frozenset({collect_name})
                reason = f"collect command from player {player_id}"
    return reason

# Backward-compatible aliases for tests
_parse_collect_stack_command = parse_collect_stack_command
_parse_collect_command = parse_collect_command
