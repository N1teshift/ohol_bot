from ohol_bot.game_data import OholObject
from ohol_bot.model import Tile
from ohol_bot.movement import is_walkable, next_walkable_step, tile_blocks_walking


def _tree() -> OholObject:
    return OholObject(object_id=63, name="Maple Tree", blocks_walking=True)


def test_tile_blocks_walking_when_object_blocks() -> None:
    tile = Tile(5, 5)
    tile_objects = {tile: 63}
    objects = {63: _tree()}

    assert tile_blocks_walking(tile, tile_objects, objects) is True
    assert is_walkable(tile, tile_objects, objects) is False


def test_empty_tile_is_walkable() -> None:
    tile = Tile(0, 0)
    assert is_walkable(tile, {}, {}) is True


def test_next_walkable_step_avoids_blocking_tree() -> None:
    start = Tile(0, 0)
    target = Tile(2, 0)
    tree_tile = Tile(1, 0)
    tile_objects = {tree_tile: 63}
    objects = {63: _tree()}

    step = next_walkable_step(start, target, tile_objects, objects)

    assert step is not None
    assert step != tree_tile


def test_next_walkable_step_routes_around_tree() -> None:
    start = Tile(0, 0)
    target = Tile(3, 0)
    tile_objects = {Tile(1, 0): 63, Tile(2, 0): 63}
    objects = {63: _tree()}

    step = next_walkable_step(start, target, tile_objects, objects)

    assert step is not None
    assert step not in {Tile(1, 0), Tile(2, 0)}


def test_next_walkable_step_returns_none_when_unreachable() -> None:
    start = Tile(0, 0)
    target = Tile(2, 0)
    tile_objects = {
        Tile(1, 0): 63,
        Tile(0, 1): 63,
        Tile(0, -1): 63,
        Tile(-1, 0): 63,
        Tile(1, 1): 63,
        Tile(1, -1): 63,
        Tile(-1, 1): 63,
        Tile(-1, -1): 63,
    }
    objects = {63: _tree()}

    assert next_walkable_step(start, target, tile_objects, objects) is None


def test_next_walkable_step_with_birth_offset() -> None:
    from ohol_bot.world_state import WorldState

    world = WorldState()
    world.birth_tile = Tile(-300, -104)
    start = Tile(21, 0)
    target = Tile(56, 0)
    tree_abs = Tile(-279, -104)
    world.tile_objects = {tree_abs: 63}
    objects = {63: _tree()}

    step_abs = next_walkable_step(
        world.to_absolute(start),
        world.to_absolute(target),
        world.tile_objects,
        objects,
    )

    assert step_abs is not None
    assert step_abs != tree_abs


def test_next_walkable_step_rejects_corner_cutting_diagonal() -> None:
    start = Tile(0, 0)
    target = Tile(2, 2)
    tile_objects = {Tile(1, 0): 63, Tile(0, 1): 63}
    objects = {63: _tree()}

    step = next_walkable_step(start, target, tile_objects, objects)

    assert step is not None
    assert step not in {Tile(1, 1)}


def test_serialize_move_avoids_tree_with_game_data() -> None:
    from ohol_bot.game_data import OholGameData
    from ohol_bot.model import Action, ActionType
    from ohol_bot.protocol_client import OholProtocolClient, serialize_action

    client = OholProtocolClient(
        game_data=OholGameData(
            objects={63: _tree()},
            transitions=(),
            biomes=__import__("ohol_bot.biomes", fromlist=["BiomeCatalog"]).BiomeCatalog({}),
        )
    )
    client._action_tile = Tile(0, 0)
    client.world_state.tile_objects = {Tile(1, 0): 63}

    message = serialize_action(
        Action(ActionType.MOVE_TO, {"x": 2, "y": 0, "sequence": 1}),
        client,
    )

    assert message.startswith("MOVE 0 0 @1 ")
    assert message != "MOVE 0 0 @1 1 0#"


def test_send_skips_move_when_blocked() -> None:
    from ohol_bot.game_data import OholGameData
    from ohol_bot.model import Action, ActionType, Observation, PlayerState
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient(
        game_data=OholGameData(
            objects={63: _tree()},
            transitions=(),
            biomes=__import__("ohol_bot.biomes", fromlist=["BiomeCatalog"]).BiomeCatalog({}),
        )
    )
    client._self_player_id_locked = True
    client._action_tile = Tile(0, 0)
    client.world_state.tile_objects = {
        Tile(1, 0): 63,
        Tile(0, 1): 63,
        Tile(0, -1): 63,
        Tile(-1, 0): 63,
        Tile(1, 1): 63,
        Tile(1, -1): 63,
        Tile(-1, 1): 63,
        Tile(-1, -1): 63,
    }
    client._last_observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=0,
            food_store=10,
            max_food_store=20,
            is_stationary=True,
        ),
    )
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client.send(Action(ActionType.MOVE_TO, {"x": 2, "y": 0}))

    assert client.sent_messages == []
    assert client._actions_sent == 0
    assert client.world_state.blocked_target_attempts.get(Tile(2, 0)) == 1
