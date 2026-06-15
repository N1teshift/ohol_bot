from ohol_bot.protocol_messages import (
    FoodChangeMessage,
    LineageMessage,
    MapChangeMessage,
    PlayerSaysMessage,
    PlayerMovementMessage,
    PlayerUpdateMessage,
    ProtocolMessageType,
    observation_from_messages,
    parse_protocol_buffer,
    parse_protocol_message,
)


def test_parse_handshake_messages() -> None:
    messages = parse_protocol_buffer(b"SN 0 challenge 437#ACCEPTED#FM#")

    assert [message.type for message in messages] == [
        ProtocolMessageType.SERVER_LOGIN,
        ProtocolMessageType.ACCEPTED,
        ProtocolMessageType.FRAME,
    ]
    assert messages[0].challenge == "challenge"
    assert messages[0].version == 437


def test_parse_player_update_and_movement() -> None:
    messages = parse_protocol_buffer(
        b"PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 48 -215 18.0 15.0 4.0#"
        b"PM\n5 51 -212 0 0#"
        b"MC\n2 1 10 20\n12 12#"
    )

    assert isinstance(messages[0], PlayerUpdateMessage)
    assert messages[0].players[0].player_id == 5
    assert messages[0].players[0].x == 48
    assert messages[0].players[0].y == -215
    assert messages[0].players[0].age == 18.0
    assert messages[0].players[0].inv_age_rate_seconds_per_year == 15.0
    assert isinstance(messages[1], PlayerMovementMessage)
    assert messages[1].players[0].x == 51
    assert messages[1].players[0].y == -212


def test_parse_food_and_map_change_messages() -> None:
    food = parse_protocol_message("FX\n18 20 0 0 3.75 -1 2 3")
    map_change = parse_protocol_message("MX\n1 -15 0 5198 -1")

    assert isinstance(food, FoodChangeMessage)
    assert food.food_store == 18
    assert food.food_capacity == 20
    assert food.yum_bonus == 2
    assert food.yum_multiplier == 3
    assert isinstance(map_change, MapChangeMessage)
    assert map_change.changes[0].object_id == 5198
    assert map_change.changes[0].x == 1
    assert map_change.changes[0].y == -15


def test_parse_craving_message() -> None:
    from ohol_bot.protocol_messages import CravingMessage, ProtocolMessageType

    message = parse_protocol_message("CR\n5198 4")

    assert isinstance(message, CravingMessage)
    assert message.type is ProtocolMessageType.CRAVING
    assert message.food_id == 5198
    assert message.yum_bonus == 4


def test_observation_from_messages_prefers_latest_player_position() -> None:
    messages = parse_protocol_buffer(
        b"PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 48 -215 18.0 15.0 4.0#"
        b"PM\n5 51 -212 0 0#"
    )

    observation = observation_from_messages(messages)

    assert observation.self.player_id == 5
    assert observation.self.tile.x == 51
    assert observation.self.tile.y == -212


def test_parse_lineage_message() -> None:
    message = parse_protocol_message("LN\n13 eve=13")

    assert isinstance(message, LineageMessage)
    assert message.type is ProtocolMessageType.LINEAGE
    assert message.player_id == 13


def test_parse_lineage_message_lists_last_line_id_only() -> None:
    message = parse_protocol_message("LN\n13 eve=13\n14 13 eve=13")

    assert isinstance(message, LineageMessage)
    assert message.player_id == 14


def test_parse_player_says_message() -> None:
    message = parse_protocol_message("PS\n8 follow")

    assert isinstance(message, PlayerSaysMessage)
    assert message.type is ProtocolMessageType.PLAYER_SAYS
    assert message.player_id == 8
    assert message.text == "follow"


def test_parse_player_says_message_with_position_fields() -> None:
    message = parse_protocol_message("PS\n8 0 0 stop follow")

    assert isinstance(message, PlayerSaysMessage)
    assert message.player_id == 8
    assert message.text == "stop follow"
