from ohol_bot.model import Action, ActionType, Tile
from ohol_bot.protocol_client import OholProtocolClient, ProtocolCredentials, serialize_action
from ohol_bot.protocol_messages import PlayerUpdateMessage, ProtocolMessageType, parse_protocol_message
from ohol_bot.world_state import WorldState


def test_serialize_protocol_probe_actions() -> None:
    assert serialize_action(Action(ActionType.SAY, {"text": "HELLO"})) == "SAY 0 0 HELLO#"
    assert serialize_action(Action(ActionType.MOVE_TO, {"x": 3, "y": -2, "sequence": 1})) == "MOVE 0 0 @1 1 0#"
    assert serialize_action(Action(ActionType.FORCE, {"x": 3, "y": -2})) == "FORCE 3 -2#"
    assert serialize_action(Action(ActionType.PICK_UP, {"x": 1, "y": 2})) == "USE 1 2#"
    assert serialize_action(Action(ActionType.DROP, {"x": 4, "y": 5})) == "DROP 4 5 -1#"
    assert (
        serialize_action(
            Action(
                ActionType.USE,
                {"held_item": None, "target_x": 7, "target_y": 8},
            )
        )
        == "USE 7 8#"
    )
    assert serialize_action(Action(ActionType.WAIT, {"ticks": 2})) == "WAIT 2#"
    assert (
        serialize_action(Action(ActionType.USE_SELF, {"x": 1, "y": 2}))
        == "SELF 1 2 -1#"
    )


def test_build_login_message_hashes_passwords() -> None:
    from ohol_bot.protocol_client import build_login_message

    message = build_login_message(
        ProtocolCredentials(
            email="bot_001@local",
            account_key="BOT01-BOT01-BOT01-BOT01",
            client_id="ohol_bot",
            server_password="",
        )
    )

    assert message.startswith("LOGIN ohol_bot bot_001@local")
    assert "da39a3ee5e6b4b0d3255bfef95601890afd80709" in message
    assert message.endswith(" 0#")


def test_incremental_frame_buffer() -> None:
    client = OholProtocolClient()
    client._ingest_bytes(b"SN 0 challenge 437#ACCEPT")
    assert len(client.parsed_messages) == 1
    assert client.parsed_messages[0].type is ProtocolMessageType.SERVER_LOGIN

    client._ingest_bytes(b"ED#FM#")
    assert len(client.parsed_messages) == 3
    assert client.parsed_messages[1].type is ProtocolMessageType.ACCEPTED
    assert client.parsed_messages[2].type is ProtocolMessageType.FRAME


def test_client_tracks_self_player_from_first_player_update() -> None:
    client = OholProtocolClient()
    client._dispatch_message(
        parse_protocol_message("PU\n13 0 0 0 0 0 0 0 0 0 0 0 0 0 10 20 18.0 15.0 4.0")
    )

    assert client.self_player_id == 13
    assert client.current_tile == Tile(10, 20)
    assert client._action_tile == Tile(10, 20)


def test_lineage_does_not_overwrite_self_player_id() -> None:
    client = OholProtocolClient()
    client._dispatch_message(
        parse_protocol_message("PU\n13 0 0 0 0 0 0 0 0 0 0 0 0 0 10 20 18.0 15.0 4.0")
    )
    client._dispatch_message(parse_protocol_message("LN\n13 eve=13\n14 13 eve=13"))

    assert client.self_player_id == 13


def test_use_self_uses_action_tile_not_stale_observation_tile() -> None:
    client = OholProtocolClient()
    client._self_player_id_locked = True
    client.self_player_id = 5
    client._action_tile = Tile(3, 0)

    message = serialize_action(Action(ActionType.USE_SELF, {"x": 2, "y": 0}), client)

    assert message == "SELF 3 0 -1#"


def test_move_serializes_one_tile_step_toward_target() -> None:
    client = OholProtocolClient()
    client._action_tile = Tile(7, 0)

    message = serialize_action(
        Action(ActionType.MOVE_TO, {"x": 11, "y": 0, "sequence": 1}),
        client,
    )

    assert message == "MOVE 7 0 @1 1 0#"
    assert client._action_tile == Tile(7, 0)


def test_move_updates_action_tile_for_followup_actions() -> None:
    client = OholProtocolClient()
    client._action_tile = Tile(2, 0)

    move = serialize_action(
        Action(ActionType.MOVE_TO, {"x": 3, "y": 0, "sequence": 1}),
        client,
    )
    eat = serialize_action(Action(ActionType.USE_SELF, {"x": 2, "y": 0}), client)

    assert move == "MOVE 2 0 @1 1 0#"
    assert eat == "SELF 2 0 -1#"


def test_client_updates_tile_from_player_movement() -> None:
    client = OholProtocolClient()
    client.self_player_id = 13
    client._dispatch_message(parse_protocol_message("PM\n13 2 -1 0 0"))

    assert client.current_tile == Tile(2, -1)


def test_world_state_exposes_chat_events() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"
        )
    )
    world.apply(parse_protocol_message("PS\n8 follow"))

    observation = world.to_observation()

    assert observation.facts["chat_events"] == (
        {"sequence": 1, "player_id": 8, "text": "follow"},
    )


def test_world_state_tracks_food_and_map_objects() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(parse_protocol_message("PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"))
    world.apply(parse_protocol_message("FX\n6 20 0 0 3.75 -1 0 0"))
    world.apply(parse_protocol_message("MX\n3 4 0 100 -1"))

    observation = world.to_observation()
    assert observation.self.food_store == 6
    assert observation.self.max_food_store == 20
    assert len(observation.nearby_objects) == 1
    assert observation.nearby_objects[0].object_id == 100


def test_world_state_tracks_yum_bonus_and_craving() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(parse_protocol_message("PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"))
    world.apply(parse_protocol_message("FX\n17 20 0 0 3.75 -1 2 3"))
    world.apply(parse_protocol_message("CR\n100 4"))

    observation = world.to_observation()
    assert observation.self.food_store == 17
    assert observation.self.yum_bonus == 2
    assert observation.self.yum_multiplier == 3
    assert observation.self.craving_food_id == 100
    assert observation.self.craving_yum_bonus == 4
    assert observation.self.is_hungry is True


def test_world_state_tracks_held_by_adult() -> None:
    world = WorldState()
    world.self_player_id = 13
    world.apply(parse_protocol_message("PU\n13 0 0 0 0 0 0 0 0 0 0 0 0 0 10 20 0.5 15.0 4.0"))
    world.apply(parse_protocol_message("PU\n42 0 0 0 0 0 -13 0 0 0 0 0 0 0 10 20 25.0 15.0 4.0"))

    observation = world.to_observation()
    assert observation.self.held_by_player_id == 42
    assert world.players[42].held_baby_id == 13


def test_parse_player_update_negative_holding_is_baby() -> None:
    message = parse_protocol_message("PU\n42 0 0 0 0 0 -13 0 0 0 0 0 0 0 10 20 25.0 15.0 4.0")

    assert isinstance(message, PlayerUpdateMessage)
    assert message.players[0].held_object_id is None
    assert message.players[0].held_baby_id == 13


def test_world_state_tracks_pending_pickup_until_pu_confirms() -> None:
    from ohol_bot.model import Action, ActionType, ObjectState, Observation, PlayerState, Tile

    world = WorldState()
    world.self_player_id = 5
    world.apply(parse_protocol_message("PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"))

    observation = Observation(
        tick=1,
        self=world.players[5],
        nearby_objects=(
            ObjectState(object_id=100, name="pie", tile=Tile(1, 2), food_value=8),
        ),
    )
    world.note_outgoing_action(Action(ActionType.PICK_UP, {"x": 1, "y": 2}), observation)

    pending = world.to_observation()
    assert pending.self.held_object_id == 100
    assert pending.self.held_pending is True
    assert pending.self.is_holding_food is True

    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 100 0 1 2 0 -1 0.5 1 0 1 2 18.0 15.0 4.0 "
            "0;0;0;0;0;0 0 -1 -1 1 0"
        )
    )
    confirmed = world.to_observation()
    assert confirmed.self.held_object_id == 100
    assert confirmed.self.held_pending is False
    assert confirmed.self.held_yum is True


def test_stale_empty_pu_does_not_clear_latched_hold() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 100 0 1 2 0 -1 0.5 1 0 1 2 18.0 15.0 4.0 "
            "0;0;0;0;0;0 0 -1 -1 1 0"
        )
    )
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 -1 0.5 0 0 3 0 18.0 15.0 4.0 "
            "0;0;0;0;0;0 0 -1 -1 0 0"
        )
    )

    observation = world.to_observation()
    assert observation.self.held_object_id == 100
    assert observation.self.held_yum is True


def test_use_self_does_not_clear_latched_hold_before_just_ate() -> None:
    from ohol_bot.model import Action, ActionType, ObjectState, Observation, Tile

    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 100 0 1 2 0 -1 0.5 1 0 1 2 18.0 15.0 4.0 "
            "0;0;0;0;0;0 0 -1 -1 1 0"
        )
    )
    observation = Observation(
        tick=1,
        self=world.players[5],
        nearby_objects=(
            ObjectState(object_id=100, name="wild berry", tile=Tile(1, 2), food_value=5),
        ),
    )
    world.note_outgoing_action(Action(ActionType.USE_SELF, {"x": 1, "y": 2}), observation)
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 -1 0.5 0 0 1 2 18.0 15.0 4.0 "
            "0;0;0;0;0;0 0 -1 -1 0 0"
        )
    )

    result = world.to_observation()
    assert result.self.held_object_id == 100
    assert result.facts["held_latched_id"] == 100


def test_pickup_pu_without_done_moving_keeps_stationary() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 18.0 15.0 4.0"
        )
    )
    assert world.players[5].is_stationary is True

    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 31 0 1 2 0 -1 0.5 0 0 2 0 18.0 15.0 4.0 "
            "0;0;0;0;0;0 0 -1 -1 1 0"
        )
    )

    observation = world.to_observation()
    assert observation.self.is_stationary is True
    assert observation.self.held_object_id == 31


def test_move_timeout_persists_stationary_in_world_state() -> None:
    import time

    from ohol_bot.world_state import MOVE_STATIONARY_TIMEOUT_SECONDS

    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"
        )
    )
    world._mark_self_moving()
    world.self_move_started_at = time.monotonic() - MOVE_STATIONARY_TIMEOUT_SECONDS - 0.1

    observation = world.to_observation()

    assert observation.self.is_stationary is True
    assert world.players[5].is_stationary is True
    assert world.self_move_started_at is None


def test_pm_at_same_tile_does_not_mark_moving() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"
        )
    )
    world.apply(parse_protocol_message("PM\n5 1 2"))

    assert world.players[5].is_stationary is True
    assert world.self_move_started_at is None


def test_outgoing_move_to_current_tile_does_not_mark_moving() -> None:
    from ohol_bot.model import Action, ActionType, Observation

    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"
        )
    )
    observation = world.to_observation()
    world.note_outgoing_action(Action(ActionType.MOVE_TO, {"x": 1, "y": 2}), observation)

    assert world.players[5].is_stationary is True
    assert world.self_move_started_at is None


def test_force_position_pu_queues_force_ack() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 1 17 0 18.0 15.0 4.0"
        )
    )

    assert world.pending_force_tile == Tile(17, 0)
    assert world.players[5].tile == Tile(17, 0)
    assert world.players[5].is_stationary is True
    assert world.take_pending_force() == Tile(17, 0)
    assert world.pending_force_tile is None


def test_client_sends_force_after_force_position_pu() -> None:
    client = OholProtocolClient()
    client.self_player_id = 5
    client.world_state.self_player_id = 5
    client._self_player_id_locked = True
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client._dispatch_message(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 1 17 0 18.0 15.0 4.0"
        )
    )

    assert client.sent_messages[-1] == "FORCE 17 0#"
    assert client.current_tile == Tile(17, 0)
    assert client._action_tile == Tile(17, 0)
    assert client._awaiting_force_ack is True


def test_send_waits_for_force_ack_before_next_move() -> None:
    client = OholProtocolClient()
    client._self_player_id_locked = True
    client._awaiting_force_ack = True
    client._last_observation = client.observe.__wrapped__ if False else None
    from ohol_bot.model import Observation, PlayerState

    client._last_observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(5, 0),
            age=1,
            food_store=10,
            max_food_store=20,
            is_stationary=True,
        ),
    )
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client.send(Action(ActionType.MOVE_TO, {"x": 10, "y": 0}))

    assert client.sent_messages == []
