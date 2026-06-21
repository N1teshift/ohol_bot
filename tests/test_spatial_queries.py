from ohol_bot.model import ObjectState, Observation, PlayerState, Tile
from ohol_bot.spatial_queries import nearest_object, object_at_tile


def _player(x: int = 0, y: int = 0) -> PlayerState:
    return PlayerState(
        player_id=1,
        tile=Tile(x, y),
        age=20.0,
        food_store=20,
        max_food_store=20,
    )


def _object(object_id: int, name: str, x: int, y: int) -> ObjectState:
    return ObjectState(object_id=object_id, name=name, tile=Tile(x, y))


def _observation(*objects: ObjectState, facts: dict | None = None) -> Observation:
    return Observation(
        tick=1,
        self=_player(),
        nearby_objects=objects,
        facts=facts or {},
    )


def test_object_at_tile_returns_matching_object() -> None:
    stone = _object(1, "Stone", 2, 0)
    observation = _observation(stone)
    assert object_at_tile(observation, Tile(2, 0)) is stone
    assert object_at_tile(observation, Tile(0, 0)) is None


def test_nearest_object_prefers_closest_by_manhattan() -> None:
    observation = _observation(
        _object(1, "Stone", 5, 0),
        _object(2, "Stone", 1, 0),
    )
    nearest = nearest_object(observation, names=frozenset({"stone"}))
    assert nearest is not None
    assert nearest.object_id == 2


def test_nearest_object_normalizes_names() -> None:
    observation = _observation(_object(1, "Round Stone", 1, 0))
    nearest = nearest_object(observation, names=frozenset({"round stone"}))
    assert nearest is not None
    assert nearest.object_id == 1


def test_nearest_object_skips_danger_tiles_by_default() -> None:
    observation = _observation(
        _object(1, "Stone", 1, 0),
        facts={
            "avoid_targets": ((1, 0),),
            "danger_tiles": (),
        },
    )
    assert nearest_object(observation, names=frozenset({"stone"})) is None


def test_nearest_object_skips_depot_tile() -> None:
    observation = _observation(_object(1, "Stone", 2, 0))
    assert (
        nearest_object(
            observation,
            names=frozenset({"stone"}),
            skip_depot=Tile(2, 0),
        )
        is None
    )


def test_nearest_object_predicate_filter() -> None:
    observation = _observation(
        _object(10, "Wild Carrot", 1, 0),
        _object(11, "Wild Carrot Plant", 2, 0),
    )
    nearest = nearest_object(
        observation,
        predicate=lambda obj: obj.object_id == 11,
        skip_danger=False,
    )
    assert nearest is not None
    assert nearest.object_id == 11


def test_observation_nearest_object_delegates() -> None:
    observation = _observation(_object(1, "Stone", 1, 0))
    nearest = observation.nearest_object(names=frozenset({"stone"}))
    assert nearest is not None
    assert nearest.object_id == 1
