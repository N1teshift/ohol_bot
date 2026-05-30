from dataclasses import replace

from ohol_bot.model import Tile
from ohol_bot.resource_memory import (
    is_priority_landmark,
    matches_collect_landmark,
)
from ohol_bot.spatial_memory import (
    SpatialMemory,
    entry_from_tile,
    remembered_target_fact,
)


def test_matches_collect_landmark() -> None:
    assert matches_collect_landmark("straight branch")
    assert matches_collect_landmark("Maple Tree")
    assert not matches_collect_landmark("@ Cutting-source Mango Tree")
    assert not matches_collect_landmark("rock")


def test_is_priority_landmark() -> None:
    assert is_priority_landmark("gooseberry", 5)
    assert is_priority_landmark("Maple Tree", 0)
    assert not is_priority_landmark("rock", 0)


def test_promote_carries_biome_id() -> None:
    memory = SpatialMemory()
    tile_objects = {Tile(10, 5): 100}
    tile_biomes = {Tile(10, 5): 0}

    memory.sync(Tile(0, 0), tile_objects, None, tick=1, tile_biomes=tile_biomes)
    memory.sync(Tile(50, 50), tile_objects, None, tick=2, tile_biomes=tile_biomes)

    assert Tile(10, 5) in memory.long_term
    assert memory.long_term[Tile(10, 5)].biome_id == 0


def test_nearest_named_collect_prefers_closest_tree() -> None:
    memory = SpatialMemory()
    memory.long_term = {
        Tile(0, 10): replace(
            entry_from_tile(Tile(0, 10), 1, None, 1, biome_id=0),
            name="Maple Tree",
        ),
        Tile(20, 0): replace(
            entry_from_tile(Tile(20, 0), 2, None, 1, biome_id=1),
            name="straight branch",
        ),
    }

    nearest = memory.nearest_named(
        memory.long_term,
        Tile(0, 0),
        names=set(),
        collect_landmarks=True,
    )
    assert nearest is not None
    assert nearest.name == "Maple Tree"


def test_remembered_target_fact_relative_coords() -> None:
    entry = entry_from_tile(Tile(15, 20), 50, None, 5, biome_id=2)
    fact = remembered_target_fact(
        entry,
        Tile(10, 20),
        lambda tile: Tile(tile.x - 10, tile.y - 5),
    )
    assert fact["rel_x"] == 5
    assert fact["rel_y"] == 15
    assert fact["abs_x"] == 15
    assert fact["biome_id"] == 2
