import pytest

from ohol_bot.manual_control import ManualCommandType, parse_command


def test_parse_move_n_direction() -> None:
    command = parse_command("move 10 east")
    assert command is not None
    assert command.type is ManualCommandType.MOVE
    assert command.steps == 10
    assert command.dx == 1
    assert command.dy == 0


def test_parse_go_direction_n() -> None:
    command = parse_command("go south 6")
    assert command is not None
    assert command.type is ManualCommandType.MOVE
    assert command.steps == 6
    assert command.dx == 0
    assert command.dy == -1


def test_parse_go_single_step() -> None:
    command = parse_command("go north")
    assert command is not None
    assert command.steps == 1
    assert command.dx == 0
    assert command.dy == 1


def test_parse_goto() -> None:
    command = parse_command("goto 12 -4")
    assert command is not None
    assert command.type is ManualCommandType.GOTO
    assert command.x == 12
    assert command.y == -4


def test_parse_status_and_quit() -> None:
    assert parse_command("status").type is ManualCommandType.STATUS
    assert parse_command("quit").type is ManualCommandType.QUIT


def test_parse_say() -> None:
    command = parse_command("say hello there")
    assert command.type is ManualCommandType.SAY
    assert command.text == "hello there"


def test_parse_empty_returns_none() -> None:
    assert parse_command("") is None
    assert parse_command("   ") is None


def test_parse_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown command"):
        parse_command("teleport 0 0")
