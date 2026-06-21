from __future__ import annotations

import sys
import time
from collections import deque
from dataclasses import dataclass

from .danger import base_object_name
from .model import Action, ActionType, Observation, ObjectState, PlayerState, Tile
from .tiles import chebyshev
from .hunger import NO_MOVE_AGE, action_blocker, can_self_act
from .map_debug import MapRenderConfig, render_observation_map
from .protocol_client import OholProtocolClient
from .spatial_memory import WORKING_RADIUS


@dataclass(frozen=True, slots=True)
class DashboardFrame:
    text: str


RATE_WINDOW_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class _CounterSample:
    at: float
    planner_tick: int | None
    world_tick: int
    server_frames: int
    ka_pings: int


class DashboardRateTracker:
    """Track counter deltas over a rolling window for per-5s rate display."""

    def __init__(self) -> None:
        self._samples: deque[_CounterSample] = deque(maxlen=64)

    def update(
        self,
        *,
        planner_tick: int | None,
        world_tick: int,
        server_frames: int,
        ka_pings: int,
        now: float | None = None,
    ) -> dict[str, float]:
        current = _CounterSample(
            at=now if now is not None else time.monotonic(),
            planner_tick=planner_tick,
            world_tick=world_tick,
            server_frames=server_frames,
            ka_pings=ka_pings,
        )
        self._samples.append(current)
        while len(self._samples) > 2 and (
            current.at - self._samples[0].at > RATE_WINDOW_SECONDS * 2
        ):
            self._samples.popleft()
        return self._rates_per_5_seconds(current)

    def _rates_per_5_seconds(self, current: _CounterSample) -> dict[str, float]:
        baseline = self._samples[0]
        for sample in self._samples:
            if current.at - sample.at >= RATE_WINDOW_SECONDS:
                baseline = sample
                break

        window = current.at - baseline.at
        if window <= 0:
            return {
                "planner": 0.0,
                "world": 0.0,
                "server_frames": 0.0,
                "ka": 0.0,
            }

        scale = RATE_WINDOW_SECONDS / window
        return {
            "planner": self._scaled_delta(
                current.planner_tick,
                baseline.planner_tick,
                scale,
            ),
            "world": max(0, current.world_tick - baseline.world_tick) * scale,
            "server_frames": max(0, current.server_frames - baseline.server_frames)
            * scale,
            "ka": max(0, current.ka_pings - baseline.ka_pings) * scale,
        }

    @staticmethod
    def _scaled_delta(
        current: int | None,
        baseline: int | None,
        scale: float,
    ) -> float:
        if current is None or baseline is None:
            return 0.0
        return max(0, current - baseline) * scale


def _dashboard_rate_tracker(client: OholProtocolClient) -> DashboardRateTracker:
    tracker = getattr(client, "dashboard_rate_tracker", None)
    if tracker is None:
        tracker = DashboardRateTracker()
        client.dashboard_rate_tracker = tracker
    return tracker


def _format_rate_per_5s(rate: float) -> str:
    if abs(rate) < 0.05:
        return " (+0/5s)"
    if abs(rate - round(rate)) < 0.05:
        return f" (+{int(round(rate))}/5s)"
    return f" (+{rate:.1f}/5s)"


def _counter_with_rate(label: str, value: int, rate: float) -> str:
    return f"{label} {value}{_format_rate_per_5s(rate)}"


def _build_header_tick(
    client: OholProtocolClient,
    observation: Observation,
    *,
    tick: int | None,
) -> str:
    rates = _dashboard_rate_tracker(client).update(
        planner_tick=tick,
        world_tick=observation.tick,
        server_frames=client.server_frames,
        ka_pings=client._sent_keep_alives,
    )
    parts: list[str] = []
    if tick is not None:
        parts.append(_counter_with_rate("planner tick", tick, rates["planner"]))
    parts.append(_counter_with_rate("world tick", observation.tick, rates["world"]))
    if client.frame_paced:
        parts.append(
            _counter_with_rate("server frames", client.server_frames, rates["server_frames"])
        )
    parts.append(_counter_with_rate("KA pings", client._sent_keep_alives, rates["ka"]))
    return "   ".join(parts)


def explain_action(observation: Observation, action: Action | None) -> str:
    if action is None:
        return "connected, waiting for first action"

    if action.type is ActionType.SAY:
        return f"saying: {action.payload.get('text', '')}"

    if action.type is ActionType.USE:
        reason = observation.facts.get("collect_reason") or observation.facts.get("follow_reason")
        if reason:
            target_x = action.payload.get("target_x")
            target_y = action.payload.get("target_y")
            return f"using tile ({target_x}, {target_y}) ({reason})"
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
        reason = observation.facts.get("collect_reason") or observation.facts.get("follow_reason")
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
        reason = observation.facts.get("collect_reason") or observation.facts.get("follow_reason")
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
        header_tick = _build_header_tick(client, observation, tick=tick)
    else:
        header_tick = _build_header_tick(client, observation, tick=None)
    elapsed = f"  elapsed {elapsed_seconds:.0f}s" if elapsed_seconds is not None else ""
    movement_mode = observation.facts.get("movement_mode", "idle")
    follow_leader_id = observation.facts.get("follow_leader_id")
    follow_distance = observation.facts.get("follow_leader_distance")
    follow_target = _format_fact_tile(observation.facts.get("follow_target"))
    follow_leader_tile = _format_fact_tile(observation.facts.get("follow_leader_tile"))
    collect_names = observation.facts.get("collect_names", ())
    collect_target = _format_fact_tile(observation.facts.get("collect_target"))
    collect_target_name = observation.facts.get("collect_target_name")
    collect_reason = observation.facts.get("collect_reason")
    collect_stack = observation.facts.get("collect_stack")
    camp_stock = observation.facts.get("camp_stock")
    camp_layout = observation.facts.get("camp_layout")
    blocked_count = len(observation.facts.get("blocked_tiles", ()))
    danger_count = len(observation.facts.get("avoid_targets", ()))
    danger_preview = observation.facts.get("danger_objects", ())
    path_diagnostics = _format_path_diagnostics(observation)
    blocker = action_blocker(observation)
    last_chat = _format_last_chat(observation)
    goal = _format_goal(
        movement_mode=movement_mode,
        leader_id=follow_leader_id,
        leader_tile=follow_leader_tile,
        leader_distance=follow_distance,
        follow_target=follow_target,
        collect_names=collect_names,
        collect_target=collect_target,
        collect_target_name=collect_target_name,
        collect_reason=collect_reason,
        collect_stack=collect_stack,
        camp_stock=camp_stock,
    )

    lines = [
        "OHOL Bot Dashboard",
        "=" * 52,
        f"Mode: {mode}{elapsed}   {header_tick}",
        f"Account: {client.credentials.email}   Player id: {client.self_player_id}",
        "",
        "Self",
        f"  Name: {player.display_name or '(unnamed)'}",
        *_format_self_lineage(player),
        f"  Position: ({player.tile.x}, {player.tile.y})   Home: {_observation_home(observation)}",
        *_format_camp_layout_lines(camp_layout, camp_stock),
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
            f"  Objects in range: {len(observation.nearby_objects)} (radius {WORKING_RADIUS})   "
            f"Blocked tiles: {blocked_count}   Danger tiles: {danger_count}"
        ),
        f"  Danger nearby: {_format_danger_preview(danger_preview)}",
        f"  Last path: {path_diagnostics}",
        f"  Nearby biomes: {_format_nearby_biomes(client, observation)}",
        "",
        "Local Tile Map",
        *(
            f"  {line}"
            for line in render_observation_map(
                observation,
                config=MapRenderConfig(radius=8, max_object_labels=4),
            ).splitlines()
        ),
        "",
        "Working memory (short)",
        *_format_working_memory_lines(observation),
        "",
        "Nearby players",
    ]

    if observation.nearby_players:
        nearby = sorted(
            observation.nearby_players,
            key=lambda other: chebyshev(player.tile, other.tile),
        )
        for other in nearby[:8]:
            distance = chebyshev(player.tile, other.tile)
            leader_mark = "  LEADER" if other.player_id == follow_leader_id else ""
            name = other.display_name or f"player {other.player_id}"
            relation_mark = f" ({other.relation_to_self})" if other.relation_to_self else ""
            race_mark = f" [{other.race_name}]" if other.race_name else ""
            lines.append(
                f"  - {name}{relation_mark}{race_mark} at ({other.tile.x}, {other.tile.y})  "
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


def _format_self_lineage(player: PlayerState) -> list[str]:
    bits: list[str] = []
    if player.mother_id is not None:
        bits.append(f"Mother: {player.mother_id}")
    if player.lineage_id is not None:
        bits.append(f"Eve line: {player.lineage_id}")
    if player.race_name:
        bits.append(f"Race: {player.race_name}")
    if not bits:
        return []
    return [f"  Lineage: {' | '.join(bits)}"]


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


def _format_working_memory_lines(observation: Observation) -> list[str]:
    """Summarize short-term spatial memory: counts and top object types."""
    working_count = len(observation.nearby_objects)
    fact_count = observation.facts.get("working_memory_count")
    if isinstance(fact_count, int):
        working_count = fact_count
    long_term_count = observation.facts.get("long_term_memory_count", 0)
    if not isinstance(long_term_count, int):
        long_term_count = 0
    unique_types = len(
        {base_object_name(obj.name) for obj in observation.nearby_objects}
    )
    promoted = observation.facts.get("memory_promoted_this_tick", 0)
    forgotten = observation.facts.get("memory_forgotten_this_tick", 0)
    lines = [
        (
            f"  Objects in working memory: {working_count} "
            f"(radius {WORKING_RADIUS}, {unique_types} types)"
        ),
        f"  Long-term landmarks: {long_term_count}",
    ]
    if isinstance(promoted, int) and promoted > 0:
        lines.append(f"  Promoted to long-term this tick: {promoted}")
    if isinstance(forgotten, int) and forgotten > 0:
        lines.append(f"  Forgotten from long-term this tick: {forgotten}")
    lines.append("  Top types in working memory:")
    top_types = _top_working_object_counts(observation, limit=10)
    if top_types:
        for name, count in top_types:
            lines.append(f"    - {name}: {count}")
    else:
        lines.append("    (none)")
    return lines


def _top_working_object_counts(
    observation: Observation,
    *,
    limit: int = 10,
) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for obj in observation.nearby_objects:
        label = base_object_name(obj.name).title()
        counts[label] = counts.get(label, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:limit]


def _observation_home(observation: Observation) -> str:
    override = observation.facts.get("home_tile")
    if isinstance(override, dict) and "x" in override and "y" in override:
        tile_text = f"({override['x']}, {override['y']})"
    else:
        tile_text = _tile_text(observation.home)
    if tile_text == "unknown":
        return tile_text
    center_name = observation.facts.get("home_center_name")
    radius = observation.facts.get("home_radius")
    if isinstance(center_name, str) and center_name:
        label = center_name.title()
        if isinstance(radius, int) and radius > 0:
            return f"{label} {tile_text}  area={radius}t"
        return f"{label} {tile_text}"
    if isinstance(radius, int) and radius > 0:
        return f"{tile_text}  area={radius}t"
    return tile_text


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


def _format_camp_layout_lines(camp_layout, camp_stock) -> list[str]:
    if not isinstance(camp_layout, dict):
        return []
    fire = camp_layout.get("fire_tile")
    fire_text = _format_fact_tile(fire)
    lines = [f"  Camp fire: {fire_text}"]
    if isinstance(camp_stock, dict) and isinstance(camp_stock.get("slots"), tuple):
        parts: list[str] = []
        for slot in camp_stock["slots"]:
            if not isinstance(slot, dict):
                continue
            slot_id = slot.get("slot_id")
            deposited = slot.get("deposited_count", 0)
            desired = slot.get("desired_count", "?")
            item = slot.get("item_name") or "item"
            if slot_id is None:
                continue
            parts.append(f"{slot_id}:{deposited}/{desired} {item}")
        if parts:
            lines.append(f"  Camp stock: {'  '.join(parts[:8])}")
    return lines


def _format_goal(
    *,
    movement_mode,
    leader_id,
    leader_tile: str,
    leader_distance,
    follow_target: str,
    collect_names,
    collect_target: str,
    collect_target_name,
    collect_reason,
    collect_stack,
    camp_stock=None,
) -> str:
    if movement_mode == "stock_camp":
        return _format_stock_camp_goal(camp_stock, collect_reason)
    if movement_mode == "collect_stack":
        return _format_collect_stack_goal(collect_stack)
    if movement_mode == "make_sharp_stone":
        detail = collect_reason or collect_target_name or "in progress"
        if collect_target != "none":
            return f"make sharp stone at {collect_target}: {detail}"
        return f"make sharp stone: {detail}"
    if movement_mode == "collect":
        target_name = _format_collect_name(collect_names, collect_target_name)
        if collect_target != "none":
            return f"trying to collect {target_name} at {collect_target}"
        return f"trying to collect {target_name}"
    if movement_mode != "follow" or leader_id is None:
        return "none"
    distance = leader_distance if leader_distance is not None else "unknown"
    return (
        f"follow target {follow_target}, leader {leader_id} at {leader_tile}, "
        f"dist={distance}"
    )


def _format_stock_camp_goal(raw, collect_reason) -> str:
    if not isinstance(raw, dict):
        return "stock camp"
    slots = raw.get("slots")
    if not isinstance(slots, tuple):
        return collect_reason or "stock camp"
    incomplete = 0
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        deposited = slot.get("deposited_count", 0)
        desired = slot.get("desired_count", 0)
        if isinstance(desired, int) and deposited < desired:
            incomplete += 1
    detail = collect_reason or f"{incomplete} slots remaining"
    return f"stock camp: {detail}"


def _format_collect_stack_goal(raw) -> str:
    if not isinstance(raw, dict):
        return "trying to collect stack"
    item_name = raw.get("item_name") or "item"
    deposited = raw.get("deposited_count", 0)
    desired = raw.get("desired_count", "?")
    depot = _format_fact_tile(raw.get("depot_tile"))
    if depot != "none":
        return f"collect stack {item_name} at {depot} ({deposited}/{desired})"
    return f"collect stack {item_name} ({deposited}/{desired})"


def _format_collect_name(collect_names, collect_target_name) -> str:
    if isinstance(collect_target_name, str) and collect_target_name:
        return collect_target_name
    if isinstance(collect_names, tuple) and collect_names:
        return "/".join(str(name) for name in collect_names)
    return "item"


def _format_last_chat(observation: Observation) -> str:
    raw = observation.facts.get("chat_events")
    if not isinstance(raw, tuple) or not raw:
        return "none"
    event = raw[-1]
    if not isinstance(event, dict):
        return "none"
    player_id = event.get("player_id", "?")
    text = event.get("text", "")
    speaker_name = event.get("speaker_name")
    label = speaker_name if speaker_name else f"player {player_id}"
    naming = event.get("naming")
    if isinstance(naming, dict):
        target_name = naming.get("display_name")
        if target_name:
            return f"{label}: {text}  -> named {target_name}"
    return f"{label}: {text}"


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


def _format_danger_preview(raw: object) -> str:
    if not isinstance(raw, tuple) or not raw:
        return "none"
    parts: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "?")
        x = item.get("x")
        y = item.get("y")
        parts.append(f"{name} ({x},{y})")
    return ", ".join(parts) if parts else "none"


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


def _format_path_diagnostics(observation: Observation) -> str:
    raw = observation.facts.get("last_path_diagnostics")
    if not isinstance(raw, dict) or not raw:
        return "none yet"
    ok = "ok" if raw.get("ok") else "failed"
    reason = raw.get("reason", "unknown")
    method = raw.get("method", "unknown")
    length = raw.get("path_length", 0)
    max_steps = raw.get("max_steps", "?")
    return f"{ok}, {method}, len={length}/{max_steps}, {reason}"
