from __future__ import annotations

import sys
from dataclasses import dataclass

from .model import Action, ActionType, Observation, ObjectState
from .hunger import NO_MOVE_AGE, action_blocker, can_self_act, forage_blocker, hunger_rule_text, is_planner_hungry
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
        if observation.self.is_hungry:
            food = observation.nearest_food()
            if food is not None and food.tile.x == target_x and food.tile.y == target_y:
                return f"moving to food: {food.name} at ({target_x}, {target_y})"
            return f"exploring east (hungry, no food visible) -> ({target_x}, {target_y})"
        if observation.home is not None and observation.self.tile.distance_to(observation.home) > 12:
            return f"returning home -> ({target_x}, {target_y})"
        branch = _nearest_named_object(observation, {"straight branch", "curved branch"})
        if branch is not None and branch.tile.x == target_x and branch.tile.y == target_y:
            return f"moving to collect {branch.name} at ({target_x}, {target_y})"
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
        blocker = action_blocker(observation) or forage_blocker(observation)
        if blocker:
            return f"waiting ({blocker})"
        if is_planner_hungry(observation.self):
            return "waiting (hungry, deciding next food action)"
        return "waiting (stomach full, nothing urgent to do)"

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
    foods = [obj for obj in observation.nearby_objects if obj.food_value > 0]
    foods.sort(key=lambda obj: player.tile.distance_to(obj.tile))

    if tick is not None:
        frame_note = (
            f"   server frames {client.server_frames}"
            if client.frame_paced
            else ""
        )
        header_tick = (
            f"planner tick {tick}   protocol msgs {observation.tick}{frame_note}"
        )
    else:
        header_tick = f"protocol msgs {observation.tick}"
    elapsed = f"  elapsed {elapsed_seconds:.0f}s" if elapsed_seconds is not None else ""
    planner_hungry = is_planner_hungry(player)
    craving_text = _format_craving(client, player)
    blocker = forage_blocker(observation)

    lines = [
        "OHOL Bot Dashboard",
        "=" * 52,
        f"Mode: {mode}{elapsed}   {header_tick}",
        f"Account: {client.credentials.email}   Player id: {client.self_player_id}",
        "",
        "Self",
        f"  Position: ({player.tile.x}, {player.tile.y})",
        f"  Age: {player.age:.2f} years (live estimate, 1yr/{observation.facts.get('age_seconds_per_year', 15):.0f}s)",
        f"  Age at last PU: {observation.facts.get('age_server_base', player.age):.2f}",
        f"  Stomach: {player.food_store}/{player.max_food_store} ({player.missing_food_pips} empty base pips)",
        f"  Yum bonus pips: +{player.yum_bonus}  (effective food: {player.effective_food_points})",
        f"  Next yum eat bonus: +{player.yum_multiplier} multiplier",
        f"  Craving: {craving_text}",
        f"  Planner hungry: {'yes' if planner_hungry else 'no'} (rule: {hunger_rule_text()})",
        f"  Can self-act: {'yes' if can_self_act(player) else f'no (need age {NO_MOVE_AGE}+)'}",
        f"  Stationary: {'yes' if player.is_stationary else 'no (finish move before eating)'}",
        f"  Eat pending: {'yes' if observation.facts.get('eat_pending') else 'no'}",
        f"  Forage blocked by: {blocker or 'nothing — will seek/eat food'}",
        f"  Held: {held_name}",
        f"  Held food: {'yes' if player.is_holding_food else 'no'}",
        f"  Carried by: {carried_by}",
        f"  Home: {_tile_text(observation.home)}",
        f"  Biome: {_format_biome(observation)}",
        "",
        "World",
        f"  Tracked tiles: {observation.facts.get('tracked_objects', 0)}",
        f"  Tracked biome tiles: {observation.facts.get('tracked_biome_tiles', 0)}",
        f"  Nearby objects: {len(observation.nearby_objects)}",
        f"  Edible nearby: {len(foods)}",
        f"  Other players nearby: {len(observation.nearby_players)}",
        f"  Nearby biomes: {_format_nearby_biomes(client, observation)}",
        "",
        "Planner",
        f"  Last action: {_action_label(last_action)}",
        f"  Reason: {explain_action(observation, last_action)}",
        "",
        "Edible nearby (closest first)",
    ]

    if foods:
        for obj in foods[:8]:
            distance = player.tile.distance_to(obj.tile)
            craving_mark = "  CRAVING" if player.craving_food_id == obj.object_id else ""
            lines.append(
                f"  - {obj.name} at ({obj.tile.x}, {obj.tile.y})  dist={distance}  "
                f"value={obj.food_value}{craving_mark}"
            )
    else:
        lines.append("  (none within range)")

    lines.extend(
        [
            "",
            "Connection",
            f"  Keep-alives sent: {client._sent_keep_alives}",
            f"  Actions sent: {client._actions_sent}",
            "",
            "Ctrl+C to stop",
        ]
    )

    return DashboardFrame(text="\n".join(lines))


def print_dashboard(frame: DashboardFrame) -> None:
    _clear_screen()
    sys.stdout.write(frame.text)
    sys.stdout.write("\n")
    sys.stdout.flush()


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


def _format_craving(client: OholProtocolClient, player) -> str:
    if player.craving_food_id is None or player.craving_food_id <= 0:
        return "none"
    name = _object_name(client, player.craving_food_id)
    bonus = player.craving_yum_bonus
    if bonus > 0:
        return f"{name} (id {player.craving_food_id}, +{bonus} multiplier if eaten)"
    return f"{name} (id {player.craving_food_id})"


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
