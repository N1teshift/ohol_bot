from ohol_bot.game_data import OholObject
from ohol_bot.model import Tile
from ohol_bot.movement import (
    blocking_footprint_tiles,
    is_walkable,
    next_walkable_step,
    tile_blocks_walking,
    walkable_path,
    walkable_path_with_diagnostics,
)


def _tree() -> OholObject:
    return OholObject(object_id=63, name="Maple Tree", blocks_walking=True)


def _wide_tree() -> OholObject:
    return OholObject(
        object_id=64,
        name="Big Maple",
        blocks_walking=True,
        left_blocking_radius=1,
        right_blocking_radius=1,
    )


def test_tile_blocks_walking_when_object_blocks() -> None:
    tile = Tile(5, 5)
    tile_objects = {tile: 63}
    objects = {63: _tree()}

    assert tile_blocks_walking(tile, tile_objects, objects) is True
    assert is_walkable(tile, tile_objects, objects) is False


def test_empty_tile_is_walkable() -> None:
    tile = Tile(0, 0)
    assert is_walkable(tile, {}, {}) is True


def test_tile_blocks_walking_from_neighbor_wide_collision() -> None:
    tree_tile = Tile(5, 5)
    blocked_neighbor = Tile(6, 5)
    tile_objects = {tree_tile: 64}
    objects = {64: _wide_tree()}

    assert tile_blocks_walking(blocked_neighbor, tile_objects, objects) is True


def test_wide_collision_does_not_block_vertical_neighbors() -> None:
    tree_tile = Tile(5, 5)
    vertical_neighbor = Tile(5, 6)
    tile_objects = {tree_tile: 64}
    objects = {64: _wide_tree()}

    assert tile_blocks_walking(vertical_neighbor, tile_objects, objects) is False


def test_blocking_footprint_uses_left_right_asymmetry() -> None:
    obj = OholObject(
        object_id=70,
        name="Asymmetric Rock",
        blocks_walking=True,
        left_blocking_radius=2,
        right_blocking_radius=0,
    )
    origin = Tile(10, 10)

    footprint = set(blocking_footprint_tiles(origin, obj))

    assert Tile(8, 10) in footprint
    assert Tile(10, 10) in footprint
    assert Tile(11, 10) not in footprint


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


def test_walkable_path_returns_short_batched_path() -> None:
    start = Tile(0, 0)
    target = Tile(10, 0)

    path = walkable_path(start, target, {}, {}, max_steps=4)

    assert path == (Tile(1, 0), Tile(2, 0), Tile(3, 0), Tile(4, 0))


def test_walkable_path_uses_diagonal_steps_when_clear() -> None:
    start = Tile(0, 0)
    target = Tile(4, 4)

    path = walkable_path(start, target, {}, {}, max_steps=4)

    assert path == (Tile(1, 1), Tile(2, 2), Tile(3, 3), Tile(4, 4))


def test_walkable_path_routes_around_tree() -> None:
    start = Tile(0, 0)
    target = Tile(3, 0)
    tile_objects = {Tile(1, 0): 63}
    objects = {63: _tree()}

    path = walkable_path(start, target, tile_objects, objects, max_steps=4)

    assert path is not None
    assert Tile(1, 0) not in path
    assert path[0] != start


def test_walkable_path_diagnostics_explain_route_method() -> None:
    start = Tile(0, 0)
    target = Tile(3, 0)
    tile_objects = {Tile(1, 0): 63}
    objects = {63: _tree()}

    result = walkable_path_with_diagnostics(
        start,
        target,
        tile_objects,
        objects,
        max_steps=4,
    )

    assert result.ok is True
    assert result.method == "bfs"
    assert result.reason == "bfs route found"
    assert Tile(1, 0) not in result.path


def test_walkable_path_diagnostics_explain_unreachable_target() -> None:
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

    result = walkable_path_with_diagnostics(start, target, tile_objects, objects)

    assert result.ok is False
    assert result.path == ()
    assert result.reason == "no route within search radius"


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


def test_send_uses_batched_move_when_path_is_clear() -> None:
    from ohol_bot.game_data import OholGameData
    from ohol_bot.model import Action, ActionType, Observation, PlayerState
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient(
        game_data=OholGameData(
            objects={},
            transitions=(),
            biomes=__import__("ohol_bot.biomes", fromlist=["BiomeCatalog"]).BiomeCatalog({}),
        )
    )
    client._self_player_id_locked = True
    client._action_tile = Tile(0, 0)
    client._last_observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=10,
            max_food_store=20,
            is_stationary=True,
        ),
    )
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client.send(Action(ActionType.MOVE_TO, {"x": 6, "y": 0}))

    assert client.sent_messages == ["MOVE 0 0 @1 1 0 2 0 3 0 4 0 5 0 6 0#"]


def test_send_uses_longer_batch_on_open_straight_path() -> None:
    from ohol_bot.game_data import OholGameData
    from ohol_bot.model import Action, ActionType, Observation, PlayerState
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient(
        game_data=OholGameData(
            objects={},
            transitions=(),
            biomes=__import__("ohol_bot.biomes", fromlist=["BiomeCatalog"]).BiomeCatalog({}),
        )
    )
    client._self_player_id_locked = True
    client._action_tile = Tile(0, 0)
    client._last_observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=10,
            max_food_store=20,
            is_stationary=True,
        ),
    )
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client.send(Action(ActionType.MOVE_TO, {"x": 10, "y": 0}))

    assert client.sent_messages == [
        "MOVE 0 0 @1 1 0 2 0 3 0 4 0 5 0 6 0 7 0 8 0 9 0 10 0#"
    ]
    assert client.world_state.feedback.last_path_diagnostics["max_steps"] == 10


def test_send_uses_short_batch_while_following() -> None:
    from ohol_bot.game_data import OholGameData
    from ohol_bot.model import Action, ActionType, Observation, PlayerState
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient(
        game_data=OholGameData(
            objects={},
            transitions=(),
            biomes=__import__("ohol_bot.biomes", fromlist=["BiomeCatalog"]).BiomeCatalog({}),
        )
    )
    client._self_player_id_locked = True
    client._action_tile = Tile(0, 0)
    client._last_observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=10,
            max_food_store=20,
            is_stationary=True,
        ),
        facts={"movement_mode": "follow"},
    )
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client.send(Action(ActionType.MOVE_TO, {"x": 6, "y": 0}))

    assert client.sent_messages == ["MOVE 0 0 @1 1 0 2 0#"]
    assert client.world_state.feedback.last_path_diagnostics["max_steps"] == 2


def test_send_uses_batched_diagonal_move_when_path_is_clear() -> None:
    from ohol_bot.game_data import OholGameData
    from ohol_bot.model import Action, ActionType, Observation, PlayerState
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient(
        game_data=OholGameData(
            objects={},
            transitions=(),
            biomes=__import__("ohol_bot.biomes", fromlist=["BiomeCatalog"]).BiomeCatalog({}),
        )
    )
    client._self_player_id_locked = True
    client._action_tile = Tile(0, 0)
    client._last_observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=10,
            max_food_store=20,
            is_stationary=True,
        ),
    )
    client.socket = type("Sock", (), {"sendall": lambda self, data: None})()

    client.send(Action(ActionType.MOVE_TO, {"x": 4, "y": 4}))

    assert client.sent_messages == ["MOVE 0 0 @1 1 1 2 2 3 3 4 4#"]


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
    assert client.world_state.feedback.last_path_diagnostics["ok"] is False
    assert (
        client.world_state.feedback.last_path_diagnostics["reason"]
        == "no route within search radius"
    )
