from ohol_bot.model import Tile
from ohol_bot.protocol_messages import parse_protocol_message
from ohol_bot.world_state import WorldState


def test_nearby_players_use_square_distance_for_diagonal_visibility() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 18.0 15.0 4.0"
        )
    )
    world.apply(
        parse_protocol_message(
            "PU\n8 0 0 0 0 0 0 0 0 0 0 0 0 0 20 20 18.0 15.0 4.0"
        )
    )

    observation = world.to_observation(radius=24)

    assert observation.self.tile == Tile(0, 0)
    assert tuple(player.player_id for player in observation.nearby_players) == (8,)
