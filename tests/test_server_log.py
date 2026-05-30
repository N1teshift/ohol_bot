from ohol_bot.server_log import ServerEventType, parse_server_log_text


def test_parse_move_say_and_use_client_messages() -> None:
    text = """
Got client message from 7: SAY 0 0 BOT_CHECK
Got client message from 7: MOVE 0 0 @1 1 0
Got client message from 7: USE 3 4
Player 7's move is done at 1,0
"""
    events = parse_server_log_text(text)

    assert [event.type for event in events] == [
        ServerEventType.SAY,
        ServerEventType.MOVE,
        ServerEventType.USE,
        ServerEventType.MOVE_DONE,
    ]
    assert events[0].player_id == 7
    assert events[3].x == 1
    assert events[3].y == 0
