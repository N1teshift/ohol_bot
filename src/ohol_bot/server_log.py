from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ServerEventType(str, Enum):
    CONNECTION = "connection"
    PLAYER_LOGIN = "player_login"
    CLIENT_MESSAGE = "client_message"
    MOVE = "move"
    SAY = "say"
    USE = "use"
    MOVE_DONE = "move_done"
    DISCONNECT = "disconnect"
    DEATH = "death"


@dataclass(frozen=True, slots=True)
class ServerEvent:
    type: ServerEventType
    line_number: int
    player_id: int | None = None
    account: str | None = None
    message: str | None = None
    x: int | None = None
    y: int | None = None


_LOGIN_RE = re.compile(
    r"New player (?P<account>\S+) connected as player (?P<player_id>\d+).*"
    r"\((?P<x>-?\d+),(?P<y>-?\d+)\)"
)
_CLIENT_MESSAGE_RE = re.compile(
    r"Got client message from (?P<player_id>\d+): (?P<message>.+)"
)
_MOVE_MESSAGE_RE = re.compile(
    r"Got client message from (?P<player_id>\d+): MOVE (?P<message>.+)"
)
_SAY_MESSAGE_RE = re.compile(
    r"Got client message from (?P<player_id>\d+): SAY (?P<message>.+)"
)
_USE_MESSAGE_RE = re.compile(
    r"Got client message from (?P<player_id>\d+): USE (?P<message>.+)"
)
_MOVE_DONE_RE = re.compile(
    r"Player (?P<player_id>\d+)'s move is done at (?P<x>-?\d+),(?P<y>-?\d+)"
)
_DISCONNECT_RE = re.compile(
    r"Player (?P<player_id>\d+) .*marked as disconnected.*"
)
_DEATH_RE = re.compile(r"Logging Eve death:|Removing all ownership .* player (?P<player_id>\d+)")


def parse_server_log_text(text: str) -> tuple[ServerEvent, ...]:
    events: list[ServerEvent] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "Got connection from" in line:
            events.append(ServerEvent(ServerEventType.CONNECTION, line_number))
            continue

        if match := _LOGIN_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.PLAYER_LOGIN,
                    line_number,
                    player_id=int(match.group("player_id")),
                    account=match.group("account"),
                    x=int(match.group("x")),
                    y=int(match.group("y")),
                )
            )
            continue

        if match := _MOVE_MESSAGE_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.MOVE,
                    line_number,
                    player_id=int(match.group("player_id")),
                    message=match.group("message"),
                )
            )
            continue

        if match := _SAY_MESSAGE_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.SAY,
                    line_number,
                    player_id=int(match.group("player_id")),
                    message=match.group("message"),
                )
            )
            continue

        if match := _USE_MESSAGE_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.USE,
                    line_number,
                    player_id=int(match.group("player_id")),
                    message=match.group("message"),
                )
            )
            continue

        if match := _CLIENT_MESSAGE_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.CLIENT_MESSAGE,
                    line_number,
                    player_id=int(match.group("player_id")),
                    message=match.group("message"),
                )
            )
            continue

        if match := _MOVE_DONE_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.MOVE_DONE,
                    line_number,
                    player_id=int(match.group("player_id")),
                    x=int(match.group("x")),
                    y=int(match.group("y")),
                )
            )
            continue

        if match := _DISCONNECT_RE.search(line):
            events.append(
                ServerEvent(
                    ServerEventType.DISCONNECT,
                    line_number,
                    player_id=int(match.group("player_id")),
                )
            )
            continue

        if match := _DEATH_RE.search(line):
            player_id = match.groupdict().get("player_id")
            events.append(
                ServerEvent(
                    ServerEventType.DEATH,
                    line_number,
                    player_id=int(player_id) if player_id else None,
                    message=line,
                )
            )

    return tuple(events)


def parse_server_log(path: str | Path) -> tuple[ServerEvent, ...]:
    return parse_server_log_text(Path(path).read_text(encoding="utf-8", errors="replace"))


def connected_accounts(events: tuple[ServerEvent, ...]) -> dict[str, int]:
    accounts: dict[str, int] = {}
    for event in events:
        if event.type is ServerEventType.PLAYER_LOGIN and event.account and event.player_id:
            accounts[event.account] = event.player_id
    return accounts
