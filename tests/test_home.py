from ohol_bot.biomes import BiomeCatalog
from ohol_bot.game_data import OholGameData, OholObject
from ohol_bot.home import (
    DEFAULT_HOME_AREA_RADIUS,
    find_home_center_near,
    is_at_home,
    is_home_center_name,
)
from ohol_bot.model import Observation, ObjectState, PlayerState, Tile


def _player(x: int, y: int) -> PlayerState:
    return PlayerState(
        player_id=5,
        tile=Tile(x, y),
        age=20.0,
        food_store=20,
        max_food_store=20,
    )


def _object(object_id: int, name: str, x: int, y: int) -> ObjectState:
    return ObjectState(object_id=object_id, name=name, tile=Tile(x, y))


def test_is_home_center_name_matches_wells_and_springs() -> None:
    assert is_home_center_name("Natural Spring# gridPlacement40")
    assert is_home_center_name("Dry Natural Spring")
    assert is_home_center_name("Eastward Gradient Dry Spring")
    assert is_home_center_name("Shallow Well# +famUse100")
    assert is_home_center_name("Deep Well")
    assert is_home_center_name("Well Site# eveSecondaryLoc")
    assert is_home_center_name("Hot Spring")
    assert is_home_center_name("Home Marker# eveHomeMarker")
    assert not is_home_center_name("Steel Spring")
    assert not is_home_center_name("Springy Wooden Door")


def test_find_home_center_near_prefers_closest_well() -> None:
    observation = Observation(
        tick=1,
        self=_player(0, 0),
        nearby_objects=(
            _object(662, "Shallow Well", 4, 0),
            _object(3030, "Natural Spring", 2, 0),
        ),
    )

    center = find_home_center_near(observation, Tile(1, 0))

    assert center is not None
    assert center.object_id == 3030
    assert center.tile == Tile(2, 0)


def test_is_at_home_uses_radius_around_center() -> None:
    observation = Observation(
        tick=1,
        self=_player(10, 0),
        home=Tile(0, 0),
        home_radius=12,
    )

    assert is_at_home(observation, Tile(10, 0))
    assert not is_at_home(observation, Tile(13, 0))


def test_home_marker_object_flag() -> None:
    game_data = OholGameData(
        objects={487: OholObject(487, "Home Marker", home_marker=True)},
        transitions=(),
        biomes=BiomeCatalog(names={0: "Grasslands"}),
    )
    observation = Observation(
        tick=1,
        self=_player(0, 0),
        nearby_objects=(_object(999, "Basket", 3, 0), _object(487, "Home Marker", 1, 0)),
    )

    center = find_home_center_near(observation, Tile(0, 0), game_data=game_data)

    assert center is not None
    assert center.object_id == 487


def test_default_home_area_radius() -> None:
    assert DEFAULT_HOME_AREA_RADIUS == 12
