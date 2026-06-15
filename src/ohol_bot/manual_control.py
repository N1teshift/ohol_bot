from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .model import Action, ActionType, Tile
from .protocol_client import OholProtocolClient

_DIRECTION_OFFSETS: dict[str, tuple[int, int]] = {
    "north": (0, 1),
    "south": (0, -1),
    "east": (1, 0),
    "west": (-1, 0),
    "n": (0, 1),
    "s": (0, -1),
    "e": (1, 0),
    "w": (-1, 0),
    "up": (0, 1),
    "down": (0, -1),
    "ne": (1, 1),
    "nw": (-1, 1),
    "se": (1, -1),
    "sw": (-1, -1),
}


class ManualCommandType(str, Enum):
    MOVE = "move"
    GOTO = "goto"
    STATUS = "status"
    PICK = "pick"
    EAT = "eat"
    DROP = "drop"
    SAY = "say"
    WAIT = "wait"
    CANCEL = "cancel"
    HELP = "help"
    QUIT = "quit"


@dataclass(frozen=True, slots=True)
class ManualCommand:
    type: ManualCommandType
    steps: int = 0
    dx: int = 0
    dy: int = 0
    x: int = 0
    y: int = 0
    text: str = ""
    ticks: int = 1


HELP_TEXT = """Manual control commands:
  move <N> <direction>     Walk N tiles (move 10 east, move 6 south)
  go <direction> [N]       Same as move; N defaults to 1 (go north, go e 5)
  goto <x> <y>             Pathfind toward tile one step at a time
  status                   Show tile, hunger, held item
  pick <x> <y>             Pick up object at tile (USE)
  eat                      Eat held food (SELF)
  drop                     Drop held item
  say <message>            Send chat
  wait [N]                 Wait N ticks (default 1)
  cancel                   Cancel current queued manual plan (play mode)
  help                     Show this help
  quit / exit              Disconnect

Directions: north/south/east/west (n/s/e/w), up/down, ne/nw/se/sw
"""


def parse_command(line: str) -> ManualCommand | None:
    stripped = line.strip()
    if not stripped:
        return None

    parts = stripped.split()
    verb = parts[0].lower()

    if verb in {"quit", "exit", "q"}:
        return ManualCommand(ManualCommandType.QUIT)
    if verb in {"help", "?"}:
        return ManualCommand(ManualCommandType.HELP)
    if verb in {"cancel", "stop"}:
        return ManualCommand(ManualCommandType.CANCEL)
    if verb in {"status", "where", "pos"}:
        return ManualCommand(ManualCommandType.STATUS)
    if verb == "eat":
        return ManualCommand(ManualCommandType.EAT)
    if verb == "drop":
        return ManualCommand(ManualCommandType.DROP)
    if verb == "say":
        return ManualCommand(ManualCommandType.SAY, text=stripped[3:].strip())
    if verb == "wait":
        ticks = 1
        if len(parts) > 1:
            ticks = _parse_positive_int(parts[1], "wait ticks")
        return ManualCommand(ManualCommandType.WAIT, ticks=ticks)
    if verb in {"pick", "pickup", "use"}:
        if len(parts) != 3:
            raise ValueError("usage: pick <x> <y>")
        return ManualCommand(
            ManualCommandType.PICK,
            x=int(parts[1]),
            y=int(parts[2]),
        )
    if verb == "goto":
        if len(parts) != 3:
            raise ValueError("usage: goto <x> <y>")
        return ManualCommand(
            ManualCommandType.GOTO,
            x=int(parts[1]),
            y=int(parts[2]),
        )
    if verb in {"move", "go", "walk"}:
        return _parse_move_command(parts[1:])

    raise ValueError(f"unknown command: {parts[0]!r} (type help)")


def _parse_move_command(args: list[str]) -> ManualCommand:
    if not args:
        raise ValueError("usage: move <N> <direction>  or  go <direction> [N]")

    if re.fullmatch(r"-?\d+", args[0]):
        steps = _parse_positive_int(args[0], "step count")
        if len(args) < 2:
            raise ValueError("usage: move <N> <direction>")
        direction = args[1].lower()
    elif len(args) >= 2 and re.fullmatch(r"-?\d+", args[1]):
        direction = args[0].lower()
        steps = _parse_positive_int(args[1], "step count")
    else:
        direction = args[0].lower()
        steps = 1

    dx, dy = _direction_offset(direction)
    return ManualCommand(ManualCommandType.MOVE, steps=steps, dx=dx, dy=dy)


def _parse_positive_int(raw: str, label: str) -> int:
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{label} must be positive, got {value}")
    return value


def _direction_offset(direction: str) -> tuple[int, int]:
    key = direction.lower()
    if key not in _DIRECTION_OFFSETS:
        options = ", ".join(sorted(set(_DIRECTION_OFFSETS)))
        raise ValueError(f"unknown direction {direction!r}; use one of: {options}")
    return _DIRECTION_OFFSETS[key]


def run_manual_control(
    client: OholProtocolClient,
    *,
    frame_paced: bool = False,
    watch: bool = False,
    prompt: str = "ohol> ",
    input_fn: Callable[[str], str] | None = None,
    print_fn: Callable[[str], None] | None = None,
    initial_commands: tuple[str, ...] = (),
) -> None:
    if not client.logged_in:
        client.login()

    client.frame_paced = frame_paced
    write = print_fn or print
    read = input_fn or (lambda p: input(p))

    write("Connected. Type help for commands.")
    pending = list(initial_commands)

    try:
        while True:
            try:
                line = pending.pop(0) if pending else read(prompt)
            except EOFError:
                break

            try:
                command = parse_command(line)
            except ValueError as exc:
                write(f"error: {exc}")
                continue

            if command is None:
                continue

            if command.type is ManualCommandType.QUIT:
                break
            if command.type is ManualCommandType.HELP:
                write(HELP_TEXT)
                continue

            try:
                message = execute_command(client, command, frame_paced=frame_paced)
            except (RuntimeError, ConnectionError) as exc:
                write(f"error: {exc}")
                continue

            if message:
                write(message)

            if watch:
                _print_watch(client, line)
    except KeyboardInterrupt:
        write("")
    finally:
        client.close()


def execute_command(
    client: OholProtocolClient,
    command: ManualCommand,
    *,
    frame_paced: bool = False,
    step_timeout_seconds: float = 30.0,
) -> str:
    if command.type is ManualCommandType.STATUS:
        observation = client.observe()
        player = observation.self
        held = player.held_object_name or (
            str(player.held_object_id) if player.held_object_id is not None else "empty"
        )
        return (
            f"tile=({player.tile.x}, {player.tile.y})  "
            f"food={player.food_store}/{player.max_food_store}  "
            f"held={held}  "
            f"stationary={player.is_stationary}"
        )

    if command.type is ManualCommandType.MOVE:
        start = client.observe().self.tile
        end = _walk_steps(
            client,
            command.dx,
            command.dy,
            command.steps,
            frame_paced=frame_paced,
            step_timeout_seconds=step_timeout_seconds,
        )
        return f"moved ({start.x}, {start.y}) -> ({end.x}, {end.y})"

    if command.type is ManualCommandType.GOTO:
        start = client.observe().self.tile
        target = Tile(command.x, command.y)
        end = _walk_to_tile(
            client,
            target,
            frame_paced=frame_paced,
            step_timeout_seconds=step_timeout_seconds,
        )
        if end == target:
            return f"arrived at ({end.x}, {end.y})"
        return f"stopped at ({end.x}, {end.y}), target was ({target.x}, {target.y})"

    if command.type is ManualCommandType.PICK:
        _send_when_ready(client, Action(ActionType.PICK_UP, {"x": command.x, "y": command.y}))
        return f"pick at ({command.x}, {command.y})"

    if command.type is ManualCommandType.EAT:
        tile = client.observe().self.tile
        _send_when_ready(client, Action(ActionType.USE_SELF, {"x": tile.x, "y": tile.y}))
        return "eat (SELF)"

    if command.type is ManualCommandType.DROP:
        tile = client.observe().self.tile
        _send_when_ready(client, Action(ActionType.DROP, {"x": tile.x, "y": tile.y}))
        return f"drop at ({tile.x}, {tile.y})"

    if command.type is ManualCommandType.SAY:
        if not command.text:
            raise ValueError("usage: say <message>")
        _send_when_ready(client, Action(ActionType.SAY, {"text": command.text}))
        return f"said: {command.text!r}"

    if command.type is ManualCommandType.WAIT:
        client.send(Action(ActionType.WAIT, {"ticks": command.ticks}))
        return f"wait {command.ticks}"

    if command.type is ManualCommandType.CANCEL:
        return "no queued plan in control mode"

    raise ValueError(f"unsupported command: {command.type}")


def _walk_steps(
    client: OholProtocolClient,
    dx: int,
    dy: int,
    steps: int,
    *,
    frame_paced: bool,
    step_timeout_seconds: float,
) -> Tile:
    for step_index in range(steps):
        _wait_for_step_window(client, frame_paced, step_timeout_seconds)
        observation = client.observe()
        current = observation.self.tile
        target = Tile(current.x + dx, current.y + dy)
        if not _send_when_ready(client, Action(ActionType.MOVE_TO, {"x": target.x, "y": target.y})):
            raise RuntimeError(
                f"move blocked on step {step_index + 1}/{steps} toward ({target.x}, {target.y})"
            )
        if not client.wait_until_stationary(step_timeout_seconds):
            raise RuntimeError(f"timed out finishing step {step_index + 1}/{steps}")
    return client.observe().self.tile


def _walk_to_tile(
    client: OholProtocolClient,
    target: Tile,
    *,
    frame_paced: bool,
    step_timeout_seconds: float,
    max_steps: int = 256,
) -> Tile:
    for _ in range(max_steps):
        observation = client.observe()
        current = observation.self.tile
        if current == target:
            return current

        _wait_for_step_window(client, frame_paced, step_timeout_seconds)
        if not _send_when_ready(
            client,
            Action(ActionType.MOVE_TO, {"x": target.x, "y": target.y}),
        ):
            return current
        if not client.wait_until_stationary(step_timeout_seconds):
            return client.observe().self.tile
    return client.observe().self.tile


def _wait_for_step_window(
    client: OholProtocolClient,
    frame_paced: bool,
    step_timeout_seconds: float,
) -> None:
    if frame_paced and not client.wait_for_frame(step_timeout_seconds):
        raise RuntimeError("timed out waiting for server frame")
    if not client.wait_until_stationary(step_timeout_seconds):
        raise RuntimeError("timed out waiting to stand still")


def _send_when_ready(client: OholProtocolClient, action: Action) -> bool:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        before = client._actions_sent
        client.send(action)
        if client._actions_sent > before:
            return True
        client._poll_once()
        client._maybe_send_keep_alive()
        time.sleep(0.01)
    return False


def _print_watch(client: OholProtocolClient, last_line: str) -> None:
    from .dashboard import format_dashboard, print_dashboard

    observation = client.observe()
    print_dashboard(
        format_dashboard(
            client,
            observation,
            last_action=Action(ActionType.SAY, {"text": last_line}),
            tick=client.server_frames,
            mode="manual-control",
        )
    )
