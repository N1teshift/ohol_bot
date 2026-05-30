import time

from ohol_bot.model import Tile
from ohol_bot.protocol_messages import parse_protocol_message
from ohol_bot.world_state import WorldState


def test_age_interpolates_between_player_updates() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 0.0 15.0 4.0"
        )
    )

    first = world.to_observation()
    assert first.self.age == 0.0
    assert first.facts["age_server_base"] == 0.0
    assert first.facts["age_seconds_per_year"] == 15.0

    time.sleep(0.15)
    second = world.to_observation()
    assert second.self.age > 0.0
    assert second.facts["age_server_base"] == 0.0
    assert second.self.age < 0.02


def test_age_resets_when_player_update_arrives() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 0.0 15.0 4.0"
        )
    )
    time.sleep(0.05)
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 1 0 0 1 2 0.1 15.0 4.0"
        )
    )

    observation = world.to_observation()
    assert observation.facts["age_server_base"] == 0.1
    assert observation.self.age >= 0.1
    assert observation.self.tile == Tile(1, 2)
