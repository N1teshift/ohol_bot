from __future__ import annotations

import sys
from dataclasses import dataclass

from .model import Action, ActionType, Observation, ObjectState
from .hunger import NO_MOVE_AGE, action_blocker, can_self_act
from .protocol_client import OholProtocolClient


@dataclass(frozen=True, slots=True)
class DashboardFrame:
    text: str


def explain_action(observation: Observation, action: Action | None) -> str:
    if action is None:
        return "connected, waiting for first action"

    if action.type is ActionType.SAY:
        return f"saying: {action.payload.get('text', '')}"

    if action.type is ActionType.USE:
        food = observation.nearest_food()
        if food is not None:
            return f"using {food.name} at ({food.tile.x}, {food.tile.y})"
        target_x = action.payload.get("target_x")
        target_y = action.payload.get("target_y")
        return f"using tile ({target_x}, {target_y})"

    if action.type is ActionType.USE_SELF:
        held_name = observation.self.held_object_name or "food"
        return f"eating held {held_name}"

    if action.type is ActionType.MOVE_TO:
        target_x = action.payload.get("x")
        target_y = action.payload.get("y")
        reason = observation.facts.get("follow_reason")
        if reason:
            return f"moving to ({target_x}, {target_y}) ({reason})"
        return f"moving to ({target_x}, {target_y})"

    if action.type is ActionType.PICK_UP:
        return f"picking up at ({action.payload.get('x')}, {action.payload.get('y')})"

    if action.type is ActionType.DROP:
        return f"dropping at ({action.payload.get('x')}, {action.payload.get('y')})"

    if action.type is ActionType.FORCE:
        return f"forcing position ({action.payload.get('x')}, {action.payload.get('y')})"

    if action.type is ActionType.WAIT:
        if observation.self.is_being_carried:
            carrier_id = observation.self.held_by_player_id
            return f"being carried by player {carrier_id}, waiting"
        blocker = action_blocker(observation)
        if blocker:
            return f"waiting ({blocker})"
        reason = observation.facts.get("follow_reason")
        return f"waiting ({reason or 'idle'})"

    return action.type.value


def format_dashboard(
    client: OholProtocolClient,
    observation: Observation,
    *,
    last_action: Action | None = None,
    tick: int | None = None,
    mode: str = "live",
    elapsed_seconds: float | None = None,
) -> DashboardFrame:
    player = observation.self
    held_name = _format_held(client, player, observation)
    carried_by = (
        f"player {player.held_by_player_id}"
        if player.is_being_carried
        else "nobody"
    )
    if tick is not None:
        frame_note = (
            f"   server frames {client.server_frames}"
            if client.frame_paced
            else ""
        )
        header_tick = (
            f"planner tick {tick}   protocol msgs {observation.tick}{frame_note}   "
            f"KA pings {client._sent_keep_alives}"
        )
    else:
        header_tick = (
            f"protocol msgs {observation.tick}   KA pings {client._sent_keep_alives}"
        )
    elapsed = f"  elapsed {elapsed_seconds:.0f}s" if elapsed_seconds is not None else ""
    movement_mode = observation.facts.get("movement_mode", "idle")
    follow_leader_id = observation.facts.get("follow_leader_id")
    follow_distance = observation.facts.get("follow_leader_distance")
    follow_target = _format_fact_tile(observation.facts.get("follow_target"))
    follow_leader_tile = _format_fact_tile(observation.facts.get("follow_leader_tile"))
    blocked_count = len(observation.facts.get("blocked_tiles", ()))
    avoid_count = len(observation.facts.get("avoid_targets", ()))
    blocker = action_blocker(observation)
    last_chat = _format_last_chat(observation)
    goal = _format_goal(
        movement_mode=movement_mode,
        leader_id=follow_leader_id,
        leader_tile=follow_leader_tile,
        leader_distance=follow_distance,
        follow_target=follow_target,
    )

    lines = [
        "OHOL Bot Dashboard",
        "=" * 52,
        f"Mode: {mode}{elapsed}   {header_tick}",
        f"Account: {client.credentials.email}   Player id: {client.self_player_id}",
        "",
        "Self",
        f"  Position: ({player.tile.x}, {player.tile.y})   Home: {_tile_text(observation.home)}",
        f"  Age: {player.age:.2f} years (live estimate, 1yr/{observation.facts.get('age_seconds_per_year', 15):.0f}s)",
        (
            f"  Can move/self-act: {'yes' if can_self_act(player) else f'no (need age {NO_MOVE_AGE}+)'}   "
            f"Stationary: {'yes' if player.is_stationary else 'no (finish current step)'}"
        ),
        f"  Action blocked by: {blocker or 'nothing'}",
        f"  Holding: {held_name}   Carried by: {carried_by}",
        f"  Biome: {_format_biome(observation)}",
        "",
        "Actions",
        f"  Goal: {goal}",
        f"  Last chat: {last_chat}",
        f"  Last action: {_action_label(last_action)}",
        f"  Actions sent: {client._actions_sent}",
        f"  Status: {explain_action(observation, last_action)}",
        "",
        "Movement Map",
        (
            f"  Tracked tiles: {observation.facts.get('tracked_objects', 0)}   "
            f"Tracked biome tiles: {observation.facts.get('tracked_biome_tiles', 0)}"
        ),
        (
            f"  Objects in range: {len(observation.nearby_objects)} (radius 24)   "
            f"Blocked tiles: {blocked_count}   Avoid targets: {avoid_count}"
        ),
        f"  Nearby biomes: {_format_nearby_biomes(client, observation)}",
        "",
        "Nearby players",
    ]

    if observation.nearby_players:
        nearby = sorted(
            observation.nearby_players,
            key=lambda other: _chebyshev(player.tile, other.tile),
        )
        for other in nearby[:8]:
            distance = _chebyshev(player.tile, other.tile)
            leader_mark = "  LEADER" if other.player_id == follow_leader_id else ""
            lines.append(
                f"  - player {other.player_id} at ({other.tile.x}, {other.tile.y})  "
                f"dist={distance}{leader_mark}"
            )
    else:
        lines.append("  (none within range)")

    foods = [obj for obj in observation.nearby_objects if obj.food_value > 0]
    if foods:
        lines.append("")
        lines.append("Food telemetry (ignored by movement mode)")
        for obj in sorted(foods, key=lambda obj: player.tile.distance_to(obj.tile))[:4]:
            distance = player.tile.distance_to(obj.tile)
            lines.append(
                f"  - {obj.name} at ({obj.tile.x}, {obj.tile.y})  dist={distance}  "
                f"value={obj.food_value}"
            )

    lines.extend(["", "Ctrl+C to stop"])

    return DashboardFrame(text="\n".join(lines))


def print_dashboard(frame: DashboardFrame, *, clear: bool = True) -> None:
    if clear:
        _clear_screen()
    sys.stdout.write(frame.text)
    sys.stdout.write("\n")
    sys.stdout.flush()


def print_dashboard_snapshot(frame: DashboardFrame) -> None:
    """Re-print the last dashboard without clearing (e.g. after Ctrl+C on Windows)."""
    print_dashboard(frame, clear=False)


def _clear_screen() -> None:
    if sys.platform == "win32":
        import os

        os.system("cls")
        return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _object_name(client: OholProtocolClient, object_id: int | None) -> str:
    if object_id is None or object_id <= 0:
        return "nothing"
    if client.game_data is not None:
        return client.game_data.object_name(object_id)
    return f"object:{object_id}"


def _format_next_yum(client: OholProtocolClient, player) -> str:
    """Craving food plus eat bonus, e.g. 'Carrot +2'; else multiplier or none."""
    if player.craving_food_id is not None and player.craving_food_id > 0:
        name = _object_name(client, player.craving_food_id)
        bonus = (
            player.craving_yum_bonus
            if player.craving_yum_bonus > 0
            else player.yum_multiplier
        )
        if bonus > 0:
            return f"{name} +{bonus}"
        return name
    if player.yum_multiplier > 0:
        return f"+{player.yum_multiplier}"
    return "none"


def _format_held(client: OholProtocolClient, player, observation: Observation) -> str:
    if player.held_object_id is not None and player.held_object_id > 0:
        name = player.held_object_name or _object_name(client, player.held_object_id)
        suffix = f" (id {player.held_object_id})"
        if player.held_pending:
            return f"{name}{suffix}, pending server confirm"
        return f"{name}{suffix}"

    if player.held_yum:
        latched = observation.facts.get("held_latched_id")
        if latched:
            name = _object_name(client, int(latched))
            return f"{name} (id {latched}, yum flag only)"
        return "yummy food (id unknown)"

    latched = observation.facts.get("held_latched_id")
    pending = observation.facts.get("held_pending_id")
    if pending:
        return f"{_object_name(client, int(pending))} (id {pending}, pending pickup)"
    if latched:
        return f"{_object_name(client, int(latched))} (id {latched}, latched)"

    return "nothing"


def _tile_text(tile) -> str:
    if tile is None:
        return "unknown"
    return f"({tile.x}, {tile.y})"


def _format_fact_tile(raw) -> str:
    if not isinstance(raw, dict):
        return "none"
    x = raw.get("x")
    y = raw.get("y")
    if x is None or y is None:
        return "none"
    return f"({x}, {y})"


def _chebyshev(a: Tile, b: Tile) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _format_goal(
    *,
    movement_mode,
    leader_id,
    leader_tile: str,
    leader_distance,
    follow_target: str,
) -> str:
    if movement_mode != "follow" or leader_id is None:
        return "none"
    distance = leader_distance if leader_distance is not None else "unknown"
    return (
        f"follow target {follow_target}, leader {leader_id} at {leader_tile}, "
        f"dist={distance}"
    )


def _format_last_chat(observation: Observation) -> str:
    raw = observation.facts.get("chat_events")
    if not isinstance(raw, tuple) or not raw:
        return "none"
    event = raw[-1]
    if not isinstance(event, dict):
        return "none"
    player_id = event.get("player_id", "?")
    text = event.get("text", "")
    return f"player {player_id}: {text}"


def _action_label(action: Action | None) -> str:
    if action is None:
        return "none yet"
    if action.type is ActionType.SAY:
        return f"say '{action.payload.get('text', '')}'"
    if action.type is ActionType.MOVE_TO:
        return f"move_to ({action.payload.get('x')}, {action.payload.get('y')})"
    if action.type is ActionType.USE:
        return f"use ({action.payload.get('target_x')}, {action.payload.get('target_y')})"
    if action.type is ActionType.USE_SELF:
        return f"use_self ({action.payload.get('x')}, {action.payload.get('y')})"
    if action.type is ActionType.PICK_UP:
        return f"pick_up ({action.payload.get('x')}, {action.payload.get('y')})"
    return action.type.value


def _nearest_named_object(observation: Observation, names: set[str]) -> ObjectState | None:
    candidates = [obj for obj in observation.nearby_objects if obj.name in names]
    if not candidates:
        return None
    return min(candidates, key=lambda obj: observation.self.tile.distance_to(obj.tile))


def _format_remembered_landmarks(observation: Observation) -> list[str]:
    lines: list[str] = []
    for label, key in (
        ("food", "nearest_remembered_food"),
        ("collect", "nearest_remembered_collect"),
    ):
        nearest = observation.facts.get(key)
        if not isinstance(nearest, dict):
            continue
        lines.append(
            f"  Nearest remembered {label}: {nearest.get('name', '?')} "
            f"at ({nearest.get('rel_x')}, {nearest.get('rel_y')})  "
            f"dist={nearest.get('distance')}  "
            f"biome={nearest.get('biome_id', '?')}"
        )
    by_biome = observation.facts.get("long_term_by_biome")
    if isinstance(by_biome, dict) and by_biome:
        top = sorted(by_biome.items(), key=lambda item: -item[1])[:3]
        summary = ", ".join(f"{name}={count}" for name, count in top)
        lines.append(f"  Remembered by biome: {summary}")
    return lines


def _format_biome(observation: Observation) -> str:
    if observation.self_biome_id is None:
        return "unknown (no map chunk yet)"
    name = observation.facts.get("self_biome_name") or f"Biome {observation.self_biome_id}"
    floor = observation.self_floor_id
    if floor is None:
        return f"{name} (id {observation.self_biome_id})"
    return f"{name} (id {observation.self_biome_id}, floor {floor})"


def _format_nearby_biomes(client: OholProtocolClient, observation: Observation) -> str:
    counts = observation.nearby_biome_counts()
    if not counts:
        return "none mapped yet"
    game_data = client.game_data
    parts: list[str] = []
    for biome_id in sorted(counts):
        if game_data is not None:
            label = game_data.biome_name(biome_id)
        else:
            label = f"Biome {biome_id}"
        parts.append(f"{label}={counts[biome_id]}")
    return ", ".join(parts)
