from __future__ import annotations

import time
import queue
import threading
from dataclasses import dataclass
from typing import Any

from .client import BotClient
from .model import Action, ActionType
from .movement import resolve_approach_tile
from .policy import Policy
from .protocol_client import OholProtocolClient


@dataclass(slots=True)
class _ManualMovePlan:
    target_x: int
    target_y: int
    steps_total: int
    steps_remaining: int
    unchanged_ticks: int = 0
    last_remaining: int | None = None


@dataclass(slots=True)
class _ManualGotoPlan:
    target_x: int
    target_y: int
    steps_remaining: int = 256
    unchanged_ticks: int = 0
    last_distance: int | None = None


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    ticks: int
    actions: tuple[Action, ...]
    survived: bool
    metrics: dict[str, float]
    stop_reason: str = "normal"
    last_dashboard: str | None = None
    events: tuple[dict[str, Any], ...] = ()


def run_episode(client: BotClient, policy: Policy, max_ticks: int) -> EpisodeResult:
    actions: list[Action] = []
    min_food_ratio = 1.0

    for tick in range(max_ticks):
        observation = client.observe()
        min_food_ratio = min(min_food_ratio, observation.self.hunger_ratio)
        if observation.self.food_store <= 0:
            return EpisodeResult(
                ticks=tick,
                actions=tuple(actions),
                survived=False,
                metrics={"min_food_ratio": min_food_ratio},
            )

        action = policy.decide(observation)
        client.send(action)
        actions.append(action)

    return EpisodeResult(
        ticks=max_ticks,
        actions=tuple(actions),
        survived=True,
        metrics={"min_food_ratio": min_food_ratio},
    )


def run_live_episode(
    client: OholProtocolClient,
    policy: Policy,
    max_ticks: int,
    *,
    tick_seconds: float = 1.0,
    frame_paced: bool = False,
    watch: bool = False,
    forever: bool = False,
) -> EpisodeResult:
    engine = LiveSessionEngine(
        client,
        policy,
        max_ticks=max_ticks,
        tick_seconds=tick_seconds,
        frame_paced=frame_paced,
        watch=watch,
        forever=forever,
    )
    return engine.run()


class LiveSessionEngine:
    """Orchestrates the live observe -> decide -> act loop."""

    def __init__(
        self,
        client: OholProtocolClient,
        policy: Policy,
        *,
        max_ticks: int,
        tick_seconds: float = 1.0,
        frame_paced: bool = False,
        watch: bool = False,
        forever: bool = False,
    ) -> None:
        self.client = client
        self.policy = policy
        self.max_ticks = max_ticks
        self.tick_seconds = tick_seconds
        self.frame_paced = frame_paced
        self.watch = watch
        self.forever = forever
        self.actions: list[Action] = []
        self.min_food_ratio = 1.0
        self.final_tile = client.current_tile
        self.interrupted = False
        self.connection_lost = False
        self.last_dashboard: str | None = None
        self.mode = "run-live (frame-paced)" if frame_paced else "run-live"

    def run(self) -> EpisodeResult:
        if not self.client.logged_in:
            self.client.login()

        self.client.frame_paced = self.frame_paced
        if self.watch:
            from .dashboard import format_dashboard, print_dashboard

            self._format_dashboard = format_dashboard
            self._print_dashboard = print_dashboard

        try:
            tick = 0
            while self.forever or tick < self.max_ticks:
                if not self._wait_for_tick():
                    continue

                observation = self.client.observe()
                self.min_food_ratio = min(self.min_food_ratio, observation.self.hunger_ratio)
                self.final_tile = observation.self.tile

                action = self.policy.decide(observation)
                self._render_dashboard(observation, action, tick=tick, mode=self.mode)

                self.client.send(action)
                self.actions.append(action)

                if not self.frame_paced and action.type is not ActionType.WAIT:
                    self.client.poll_until(self.tick_seconds)

                tick += 1
        except KeyboardInterrupt:
            self.interrupted = True
        except ConnectionError:
            self.connection_lost = True
        finally:
            self.client.close()

        return self._final_result()

    def _wait_for_tick(self) -> bool:
        if self.frame_paced:
            return self.client.wait_for_frame()
        self.client.poll_until(self.tick_seconds)
        return True

    def _render_dashboard(self, observation, action: Action | None, *, tick: int, mode: str) -> None:
        if not self.watch:
            return
        frame = self._format_dashboard(
            self.client,
            observation,
            last_action=action,
            tick=tick,
            mode=mode,
        )
        self._print_dashboard(frame)
        self.last_dashboard = frame.text

    def _final_result(self) -> EpisodeResult:
        stop_reason = (
            "keyboard_interrupt"
            if self.interrupted
            else "connection_lost"
            if self.connection_lost
            else "normal"
        )
        if self.connection_lost and self.watch:
            print("\nConnection closed by server.")
        return EpisodeResult(
            ticks=len(self.actions),
            actions=tuple(self.actions),
            survived=not self.connection_lost,
            metrics={
                "min_food_ratio": self.min_food_ratio,
                "final_x": float(self.final_tile.x),
                "final_y": float(self.final_tile.y),
                "server_frames": float(self.client.server_frames),
            },
            stop_reason=stop_reason,
            last_dashboard=self.last_dashboard,
        )


def run_live_interactive_episode(
    client: OholProtocolClient,
    policy: Policy,
    max_ticks: int,
    *,
    tick_seconds: float = 1.0,
    frame_paced: bool = True,
    watch: bool = True,
    forever: bool = True,
) -> EpisodeResult:
    """Run autopilot with one-shot manual command overrides.

    Commands are read from stdin in a background thread and executed with
    priority over planner actions for one iteration, then control returns to
    autopilot.
    """
    from .dashboard import format_dashboard, print_dashboard
    from .manual_control import HELP_TEXT, ManualCommandType, parse_command

    if not client.logged_in:
        client.login()

    client.frame_paced = frame_paced
    actions: list[Action] = []
    min_food_ratio = 1.0
    final_tile = client.current_tile
    last_dashboard: str | None = None
    interrupted = False
    connection_lost = False
    mode = "play"
    control_mode = "auto"

    command_queue: "queue.Queue[str]" = queue.Queue()
    stop_event = threading.Event()
    manual_plan: _ManualMovePlan | _ManualGotoPlan | None = None
    previous_manual_tile = None
    play_events: list[dict[str, Any]] = []

    def _reader() -> None:
        while not stop_event.is_set():
            try:
                line = input("cmd> ")
            except EOFError:
                stop_event.set()
                return
            command_queue.put(line)

    reader = threading.Thread(target=_reader, name="manual-input", daemon=True)
    reader.start()
    print(
        "Interactive mode: AUTO is movement idle/follow. Say 'follow' in game to start following, "
        "or type 'manual' for terminal control."
    )

    try:
        tick = 0
        while forever or tick < max_ticks:
            if frame_paced:
                if not client.wait_for_frame():
                    continue
            else:
                client.poll_until(tick_seconds)

            observation = client.observe()
            min_food_ratio = min(min_food_ratio, observation.self.hunger_ratio)
            final_tile = observation.self.tile

            last_action: Action | None = None
            command_line: str | None = None
            try:
                command_line = command_queue.get_nowait()
            except queue.Empty:
                command_line = None

            if command_line is not None:
                mode_switch = _parse_control_mode_switch(command_line)
                if mode_switch is not None:
                    control_mode = mode_switch
                    if control_mode == "auto":
                        manual_plan = None
                        previous_manual_tile = None
                    print(f"control mode: {control_mode}")
                    play_events.append(
                        {
                            "tick": tick,
                            "event": "control_mode_switch",
                            "mode": control_mode,
                        }
                    )
                    last_action = Action(
                        ActionType.SAY,
                        {"text": f"mode: {control_mode}"},
                    )
                    if watch:
                        mode_label = _mode_label(mode, control_mode, manual_plan)
                        frame = format_dashboard(
                            client,
                            client.observe(),
                            last_action=last_action,
                            tick=tick,
                            mode=mode_label,
                        )
                        print_dashboard(frame)
                        last_dashboard = frame.text
                    tick += 1
                    continue

                try:
                    command = parse_command(command_line)
                except ValueError as exc:
                    print(f"error: {exc}")
                    command = None

                if command is not None:
                    if command.type is ManualCommandType.QUIT:
                        play_events.append({"tick": tick, "event": "manual_quit"})
                        break
                    if command.type is ManualCommandType.HELP:
                        print(HELP_TEXT)
                    elif command.type is ManualCommandType.STATUS:
                        player = observation.self
                        held = player.held_object_name or (
                            str(player.held_object_id)
                            if player.held_object_id is not None
                            else "empty"
                        )
                        print(
                            f"tile=({player.tile.x}, {player.tile.y})  "
                            f"food={player.food_store}/{player.max_food_store}  "
                            f"held={held}  stationary={player.is_stationary}"
                        )
                    elif control_mode == "auto":
                        print("manual command ignored in auto mode (type 'manual' first)")
                        play_events.append(
                            {
                                "tick": tick,
                                "event": "manual_ignored_auto_mode",
                                "command": command_line.strip(),
                            }
                        )
                    elif command.type is ManualCommandType.MOVE:
                        current = observation.self.tile
                        raw_target = Action(
                            ActionType.MOVE_TO,
                            {
                                "x": current.x + command.dx * command.steps,
                                "y": current.y + command.dy * command.steps,
                            },
                        )
                        target_tile = _resolve_manual_target_tile(client, current, raw_target)
                        target_x = target_tile.x
                        target_y = target_tile.y
                        manual_plan = _ManualMovePlan(
                            target_x=target_x,
                            target_y=target_y,
                            steps_total=command.steps,
                            steps_remaining=command.steps,
                        )
                        previous_manual_tile = current
                        print(
                            f"manual override queued: move {command.steps} step(s) to ({target_x}, {target_y})"
                        )
                        play_events.append(
                            {
                                "tick": tick,
                                "event": "manual_plan_move",
                                "steps": command.steps,
                                "dx": command.dx,
                                "dy": command.dy,
                            }
                        )
                    elif command.type is ManualCommandType.GOTO:
                        target_tile = _resolve_manual_target_tile(
                            client,
                            observation.self.tile,
                            Action(ActionType.MOVE_TO, {"x": command.x, "y": command.y}),
                        )
                        manual_plan = _ManualGotoPlan(
                            target_x=target_tile.x,
                            target_y=target_tile.y,
                        )
                        previous_manual_tile = observation.self.tile
                        print(
                            f"manual override queued: goto ({target_tile.x}, {target_tile.y})"
                        )
                        play_events.append(
                            {
                                "tick": tick,
                                "event": "manual_plan_goto",
                                "x": command.x,
                                "y": command.y,
                            }
                        )
                    elif command.type is ManualCommandType.CANCEL:
                        if manual_plan is None:
                            print("no manual plan to cancel")
                            play_events.append({"tick": tick, "event": "manual_cancel_noop"})
                        else:
                            manual_plan = None
                            previous_manual_tile = None
                            print("manual plan cancelled")
                            play_events.append({"tick": tick, "event": "manual_plan_cancelled"})
                    else:
                        immediate = _manual_command_to_action(command, observation)
                        if immediate is None:
                            print("error: unsupported manual command")
                            play_events.append(
                                {
                                    "tick": tick,
                                    "event": "manual_command_error",
                                    "command": command_line.strip(),
                                }
                            )
                        elif _try_send_action(client, immediate):
                            play_events.append(
                                {
                                    "tick": tick,
                                    "event": "manual_action_sent",
                                    "command": command_line.strip(),
                                    "action": immediate.type.value,
                                }
                            )
                        else:
                            print("manual action deferred (busy), try again")
                            play_events.append(
                                {
                                    "tick": tick,
                                    "event": "manual_action_deferred",
                                    "command": command_line.strip(),
                                }
                            )
                    last_action = Action(
                        ActionType.SAY,
                        {"text": f"manual: {command_line.strip()}"},
                    )

            if command_line is None:
                planned_action: Action | None = None
                if control_mode == "manual" and isinstance(manual_plan, _ManualMovePlan):
                    current = observation.self.tile
                    if current.x == manual_plan.target_x and current.y == manual_plan.target_y:
                        manual_plan = None
                        previous_manual_tile = None
                    elif manual_plan.steps_remaining <= 0:
                        manual_plan = None
                        previous_manual_tile = None
                    else:
                        planned_action = Action(
                            ActionType.MOVE_TO,
                            {"x": manual_plan.target_x, "y": manual_plan.target_y},
                        )
                elif control_mode == "manual" and isinstance(manual_plan, _ManualGotoPlan):
                    current = observation.self.tile
                    if (
                        current.x == manual_plan.target_x
                        and current.y == manual_plan.target_y
                    ) or manual_plan.steps_remaining <= 0:
                        manual_plan = None
                        previous_manual_tile = None
                    else:
                        planned_action = Action(
                            ActionType.MOVE_TO,
                            {"x": manual_plan.target_x, "y": manual_plan.target_y},
                        )

                if planned_action is not None:
                    last_action = planned_action
                    if _try_send_action(client, planned_action):
                        current = observation.self.tile
                        if isinstance(manual_plan, _ManualMovePlan):
                            remaining = max(
                                abs(manual_plan.target_x - current.x),
                                abs(manual_plan.target_y - current.y),
                            )
                            if (
                                manual_plan.last_remaining is not None
                                and remaining >= manual_plan.last_remaining
                            ):
                                manual_plan.unchanged_ticks += 1
                            else:
                                manual_plan.unchanged_ticks = 0
                            manual_plan.last_remaining = remaining
                            manual_plan.steps_remaining = remaining
                            previous_manual_tile = current
                            if manual_plan.unchanged_ticks >= 12:
                                print("manual move cancelled: no progress")
                                manual_plan = None
                                previous_manual_tile = None
                            if manual_plan.steps_remaining <= 0:
                                manual_plan = None
                                previous_manual_tile = None
                        elif isinstance(manual_plan, _ManualGotoPlan):
                            distance = max(
                                abs(manual_plan.target_x - current.x),
                                abs(manual_plan.target_y - current.y),
                            )
                            if (
                                manual_plan.last_distance is not None
                                and distance >= manual_plan.last_distance
                            ):
                                manual_plan.unchanged_ticks += 1
                            else:
                                manual_plan.unchanged_ticks = 0
                            manual_plan.last_distance = distance
                            manual_plan.steps_remaining -= 1
                            previous_manual_tile = current
                            if manual_plan.unchanged_ticks >= 12:
                                print("manual goto cancelled: no progress")
                                manual_plan = None
                                previous_manual_tile = None
                        actions.append(planned_action)
                        play_events.append(
                            {
                                "tick": tick,
                                "event": "manual_step_sent",
                                "action": planned_action.type.value,
                                "x": planned_action.payload.get("x"),
                                "y": planned_action.payload.get("y"),
                            }
                        )
                        last_action = planned_action
                    else:
                        # keep plan; retry on next frame
                        pass
                else:
                    if control_mode == "auto":
                        action = policy.decide(observation)
                        client.send(action)
                        actions.append(action)
                        play_events.append(
                            {
                                "tick": tick,
                                "event": "autopilot_action",
                                "action": action.type.value,
                            }
                        )
                        last_action = action

                        if not frame_paced and action.type is not ActionType.WAIT:
                            client.poll_until(tick_seconds)

            if command_line is not None:
                # keep cadence and rendering after manual command processing
                pass

            if watch:
                mode_label = _mode_label(mode, control_mode, manual_plan)
                frame = format_dashboard(
                    client,
                    observation,
                    last_action=last_action,
                    tick=tick,
                    mode=mode_label,
                )
                print_dashboard(frame)
                last_dashboard = frame.text

            tick += 1
    except KeyboardInterrupt:
        interrupted = True
    except ConnectionError:
        connection_lost = True
    finally:
        stop_event.set()
        client.close()

    stop_reason = (
        "keyboard_interrupt"
        if interrupted
        else "connection_lost"
        if connection_lost
        else "manual_quit"
        if not interrupted and not connection_lost
        else "normal"
    )
    return EpisodeResult(
        ticks=len(actions),
        actions=tuple(actions),
        survived=not connection_lost,
        metrics={
            "min_food_ratio": min_food_ratio,
            "final_x": float(final_tile.x),
            "final_y": float(final_tile.y),
            "server_frames": float(client.server_frames),
        },
        stop_reason=stop_reason,
        last_dashboard=last_dashboard,
        events=tuple(play_events),
    )


def _try_send_action(client: OholProtocolClient, action: Action) -> bool:
    before = client._actions_sent
    client.send(action)
    return client._actions_sent > before


def _manual_command_to_action(command, observation) -> Action | None:
    command_type = getattr(command.type, "value", str(command.type))
    if command_type == "pick":
        return Action(ActionType.PICK_UP, {"x": command.x, "y": command.y})
    if command_type == "eat":
        tile = observation.self.tile
        return Action(ActionType.USE_SELF, {"x": tile.x, "y": tile.y})
    if command_type == "drop":
        tile = observation.self.tile
        return Action(ActionType.DROP, {"x": tile.x, "y": tile.y})
    if command_type == "say" and command.text:
        return Action(ActionType.SAY, {"text": command.text})
    if command_type == "wait":
        return Action(ActionType.WAIT, {"ticks": command.ticks})
    return None


def _parse_control_mode_switch(line: str) -> str | None:
    lowered = line.strip().lower()
    if lowered == "auto":
        return "auto"
    if lowered == "manual":
        return "manual"
    return None


def _mode_label(
    base_mode: str,
    control_mode: str,
    manual_plan: _ManualMovePlan | _ManualGotoPlan | None,
) -> str:
    label = f"{base_mode} [{control_mode}]"
    if control_mode != "manual":
        return label
    if isinstance(manual_plan, _ManualMovePlan):
        return (
            f"{label} (move: {manual_plan.steps_remaining}/{manual_plan.steps_total} left "
            f"to ({manual_plan.target_x}, {manual_plan.target_y}))"
        )
    if isinstance(manual_plan, _ManualGotoPlan):
        return (
            f"{label} (goto: ({manual_plan.target_x}, {manual_plan.target_y}), "
            f"{manual_plan.steps_remaining} left)"
        )
    return label


def _resolve_manual_target_tile(
    client: OholProtocolClient,
    current: object,
    action: Action,
):
    target_x = int(action.payload["x"])
    target_y = int(action.payload["y"])
    if client.game_data is None:
        from .model import Tile

        return Tile(target_x, target_y)

    from .model import Tile

    start = Tile(int(current.x), int(current.y))
    target = Tile(target_x, target_y)
    start_abs = client.world_state.to_absolute(start)
    target_abs = client.world_state.to_absolute(target)
    blocked_abs = {
        client.world_state.to_absolute(tile) for tile in client.world_state.blocked_tiles
    }
    resolved_abs = resolve_approach_tile(
        target_abs,
        start_abs,
        client.world_state.tile_objects,
        client.game_data.objects,
        blocked_tiles=blocked_abs,
    )
    if resolved_abs is None:
        return target
    return client.world_state.to_relative(resolved_abs)
