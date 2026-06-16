from ohol_bot.biomes import BiomeCatalog
from ohol_bot.game_data import OholGameData, OholObject
from ohol_bot.model import Tile
from ohol_bot.protocol_messages import parse_protocol_message
from ohol_bot.world_state import WorldState


def _wolf_game_data() -> OholGameData:
    return OholGameData(
        objects={900: OholObject(object_id=900, name="Wolf", deadly_distance=1)},
        transitions=(),
        biomes=BiomeCatalog(names={0: "Grasslands"}),
    )


def test_stale_last_move_target_does_not_create_avoid_marks() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 18.0 15.0 4.0"
        )
    )
    world.feedback.last_move_target = Tile(5, 5)

    observation = world.to_observation()
    for _ in range(6):
        observation = world.to_observation()

    assert observation.facts["avoid_targets"] == ()
    assert observation.facts["danger_tiles"] == ()


def test_to_observation_exposes_danger_tiles_from_nearby_animals() -> None:
    world = WorldState()
    world.self_player_id = 5
    world.apply(
        parse_protocol_message(
            "PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 18.0 15.0 4.0"
        )
    )
    wolf_tile = Tile(2, 0)
    world.tile_objects[wolf_tile] = 900

    observation = world.to_observation(_wolf_game_data())

    assert observation.facts["avoid_targets"] == ((2, 0),)
    assert observation.facts["danger_tiles"] == ((2, 0),)
    assert observation.facts["danger_objects"] == (
        {"x": 2, "y": 0, "name": "Wolf"},
    )
    assert world.avoid_targets == {Tile(2, 0)}
