from ohol_bot.biomes import count_biomes_in_radius, nearest_tile_with_biome
from ohol_bot.game_data import parse_object_file
from ohol_bot.model import Tile
from ohol_bot.protocol_messages import parse_protocol_message
from ohol_bot.world_state import WorldState


def test_map_chunk_stores_biome_and_floor_per_tile() -> None:
    world = WorldState()
    world.apply(
        parse_protocol_message(
            "MC\n3 1 10 20\n15 15\n__PAYLOAD__\n"
            "0:10:100 2:11:0 3:12:50"
        )
    )

    assert world.biome_at(Tile(10, 20)) == 0
    assert world.floor_at(Tile(10, 20)) == 10
    assert world.tile_objects[Tile(10, 20)] == 100

    assert world.biome_at(Tile(11, 20)) == 2
    assert world.floor_at(Tile(11, 20)) == 11
    assert Tile(11, 20) not in world.tile_objects

    assert world.biome_at(Tile(12, 20)) == 3
    assert world.tile_objects[Tile(12, 20)] == 50


def test_map_change_updates_floor_without_dropping_biome() -> None:
    world = WorldState()
    world.apply(
        parse_protocol_message(
            "MC\n1 1 5 5\n8 8\n__PAYLOAD__\n0:20:30"
        )
    )
    world.apply(parse_protocol_message("MX\n5 5 21 31"))

    assert world.biome_at(Tile(5, 5)) == 0
    assert world.floor_at(Tile(5, 5)) == 21
    assert world.tile_objects[Tile(5, 5)] == 31


def test_observation_exposes_self_and_nearby_biomes() -> None:
    from ohol_bot.game_data import load_game_data
    from pathlib import Path

    root = Path(".ohol_runtime/server")
    if not root.exists():
        return

    world = WorldState()
    world.self_player_id = 1
    world.apply(parse_protocol_message("PU\n1 0 0 0 0 0 0 0 0 0 0 0 0 0 10 20 18.0 60.0 4.0"))
    world.apply(
        parse_protocol_message(
            "MC\n3 1 9 20\n15 15\n__PAYLOAD__\n"
            "0:10:0 0:10:0 0:10:0"
        )
    )

    game_data = load_game_data(root)
    observation = world.to_observation(game_data)

    assert observation.self_biome_id == 0
    assert observation.self_floor_id == 10
    assert observation.facts["self_biome_name"] == "Grasslands"
    assert observation.nearby_biome_counts()[0] == 3
    assert all(obj.biome_id == 0 for obj in observation.nearby_objects)


def test_nearest_tile_with_biome_prefers_closest() -> None:
    tile_biomes = {
        Tile(0, 0): 0,
        Tile(5, 0): 2,
        Tile(2, 0): 2,
    }

    assert nearest_tile_with_biome(tile_biomes, Tile(0, 0), 2) == Tile(2, 0)


def test_parse_object_spawn_biomes(tmp_path) -> None:
    object_file = tmp_path / "50.txt"
    object_file.write_text(
        "\n".join(
            [
                "id=50",
                "Milkweed",
                "mapChance=2.000000#biomes_0",
            ]
        ),
        encoding="utf-8",
    )

    obj = parse_object_file(object_file)

    assert obj.spawn_biomes == frozenset({0})


def test_biome_catalog_loads_from_sandbox() -> None:
    from pathlib import Path

    from ohol_bot.biomes import load_biome_catalog

    root = Path(".ohol_runtime/server")
    if not root.exists():
        return

    catalog = load_biome_catalog(root)

    assert catalog.biome_name(0) == "Grasslands"
    assert 0 in catalog.order
    assert catalog.special_biome_ids
