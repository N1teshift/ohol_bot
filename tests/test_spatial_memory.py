from ohol_bot.model import Action, ActionType, ObjectState, Observation, PlayerState, Tile
from ohol_bot.protocol_messages import parse_protocol_message
from ohol_bot.spatial_memory import (
    LONG_TERM_MAX_ENTRIES,
    LONG_TERM_STALE_TICKS,
    SpatialMemory,
    WORKING_RADIUS,
    entry_from_tile,
)
from ohol_bot.world_state import WorldState


def _food_at(abs_x: int, abs_y: int, object_id: int = 100) -> dict[Tile, int]:
    return {Tile(abs_x, abs_y): object_id}


def test_tile_inside_radius_in_working_not_long_term() -> None:
    memory = SpatialMemory()
    center = Tile(0, 0)
    tile_objects = _food_at(5, 0)

    memory.sync(center, tile_objects, None, tick=1, radius=WORKING_RADIUS)

    assert Tile(5, 0) in memory.working
    assert Tile(5, 0) not in memory.long_term
    assert memory.working[Tile(5, 0)].object_id == 100


def test_leaving_radius_promotes_to_long_term() -> None:
    memory = SpatialMemory()
    tile_objects = _food_at(5, 0)

    memory.sync(Tile(0, 0), tile_objects, None, tick=1)
    assert Tile(5, 0) in memory.working

    memory.sync(Tile(50, 50), tile_objects, None, tick=2)

    assert Tile(5, 0) not in memory.working
    assert Tile(5, 0) in memory.long_term
    assert memory.long_term[Tile(5, 0)].last_seen_tick == 2


def test_reentering_radius_removes_from_long_term() -> None:
    memory = SpatialMemory()
    tile_objects = _food_at(5, 0)

    memory.sync(Tile(0, 0), tile_objects, None, tick=1)
    memory.sync(Tile(50, 50), tile_objects, None, tick=2)
    assert Tile(5, 0) in memory.long_term

    memory.sync(Tile(0, 0), tile_objects, None, tick=3)

    assert Tile(5, 0) in memory.working
    assert Tile(5, 0) not in memory.long_term


def test_forget_tile_clears_both_stores() -> None:
    memory = SpatialMemory()
    tile = Tile(10, 10)
    memory.working[tile] = entry_from_tile(tile, 50, None, tick=1)
    memory.long_term[tile] = entry_from_tile(tile, 50, None, tick=1)

    assert memory.forget_tile(tile) is True
    assert tile not in memory.working
    assert tile not in memory.long_term


def test_stale_long_term_eviction() -> None:
    memory = SpatialMemory()
    old_tile = Tile(100, 100)
    memory.long_term[old_tile] = entry_from_tile(old_tile, 1, None, tick=0)

    forgotten = memory._evict_stale(LONG_TERM_STALE_TICKS + 1)

    assert forgotten == 1
    assert old_tile not in memory.long_term


def test_long_term_cap_eviction() -> None:
    memory = SpatialMemory()
    for index in range(LONG_TERM_MAX_ENTRIES + 5):
        tile = Tile(index, 0)
        memory.long_term[tile] = entry_from_tile(tile, 1, None, tick=index)

    forgotten = memory._enforce_cap()

    assert forgotten == 5
    assert len(memory.long_term) == LONG_TERM_MAX_ENTRIES
    assert Tile(0, 0) not in memory.long_term
    assert Tile(LONG_TERM_MAX_ENTRIES + 4, 0) in memory.long_term


def test_world_state_mx_clear_forgets_memory() -> None:
    world = WorldState()
    world.apply(
        parse_protocol_message(
            "MC\n1 1 10 10\n8 8\n__PAYLOAD__\n0:20:100"
        )
    )
    world.self_player_id = 1
    world.players[1] = PlayerState(
        player_id=1,
        tile=Tile(0, 0),
        age=20,
        food_store=4,
        max_food_store=4,
    )
    world.to_observation()
    assert Tile(10, 10) in world.spatial_memory.working

    world.apply(parse_protocol_message("MX\n10 10 21 0"))

    assert Tile(10, 10) not in world.tile_objects
    assert Tile(10, 10) not in world.spatial_memory.working
    assert Tile(10, 10) not in world.spatial_memory.long_term


def test_world_state_pickup_forgets_tile() -> None:
    world = WorldState()
    world.self_player_id = 1
    world.birth_tile = Tile(0, 0)
    world.players[1] = PlayerState(
        player_id=1,
        tile=Tile(0, 0),
        age=20,
        food_store=4,
        max_food_store=4,
    )
    world.tile_objects[Tile(1, 0)] = 100
    world.spatial_memory.sync(Tile(0, 0), world.tile_objects, None, tick=1)

    observation = Observation(
        tick=1,
        self=world.players[1],
        nearby_objects=(
            ObjectState(
                object_id=100,
                name="test-food",
                tile=Tile(1, 0),
                food_value=5,
            ),
        ),
    )
    world.note_outgoing_action(
        Action(ActionType.PICK_UP, {"x": 1, "y": 0}),
        observation,
    )

    assert Tile(1, 0) not in world.spatial_memory.working
    assert Tile(1, 0) not in world.spatial_memory.long_term


def test_observation_exposes_memory_facts() -> None:
    world = WorldState()
    world.self_player_id = 1
    world.birth_tile = Tile(0, 0)
    world.players[1] = PlayerState(
        player_id=1,
        tile=Tile(50, 0),
        age=20,
        food_store=4,
        max_food_store=4,
    )
    world.tile_objects[Tile(5, 0)] = 100
    world.spatial_memory.sync(Tile(0, 0), world.tile_objects, None, tick=1)
    world.spatial_memory.sync(Tile(50, 0), world.tile_objects, None, tick=2)

    observation = world.to_observation()

    assert observation.facts["working_memory_count"] >= 0
    assert observation.facts["long_term_memory_count"] == 1
    assert observation.facts["memory_promoted_this_tick"] >= 0


def test_working_entry_has_biome_from_tile_biomes() -> None:
    memory = SpatialMemory()
    memory.sync(
        Tile(0, 0),
        {Tile(3, 0): 50},
        None,
        tick=1,
        tile_biomes={Tile(3, 0): 1},
    )
    assert memory.working[Tile(3, 0)].biome_id == 1
