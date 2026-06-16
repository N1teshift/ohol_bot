from ohol_bot.biomes import BiomeCatalog
from ohol_bot.danger import (
    DANGEROUS_NAME_PHRASES,
    base_object_name,
    danger_near_route,
    danger_path_blockers,
    dangerous_objects_preview,
    dangerous_tiles,
    is_dangerous_name,
    is_dangerous_object,
)
from ohol_bot.game_data import OholGameData, OholObject
from ohol_bot.model import ObjectState, Tile


def _game_data(*objects: OholObject) -> OholGameData:
    return OholGameData(
        objects={obj.object_id: obj for obj in objects},
        transitions=(),
        biomes=BiomeCatalog(names={0: "Grasslands"}),
    )


def test_is_dangerous_name_matches_ohol_variant_names() -> None:
    assert is_dangerous_name("Wolf")
    assert is_dangerous_name("Mosquito Swarm")
    assert is_dangerous_name("Mosquito Swarm#just bit")
    assert is_dangerous_name("Wild Boar")
    assert is_dangerous_name("Attacking Wild Boar")
    assert is_dangerous_name("Grizzly Bear")
    assert is_dangerous_name("Rattle Snake")
    assert is_dangerous_name("Attacking Rattle Snake")
    assert not is_dangerous_name("Wolf Skin")
    assert not is_dangerous_name("Dead Boar# no arrow")
    assert not is_dangerous_name("Mosquito Smash Working")
    assert not is_dangerous_name("Snake Skin")
    assert not is_dangerous_name("Snake Roadkill")


def test_base_object_name_strips_variant_suffix() -> None:
    assert base_object_name("Mosquito Swarm#just bit") == "mosquito swarm"


def test_is_dangerous_object_uses_deadly_distance_from_game_data() -> None:
    game_data = _game_data(
        OholObject(2156, "Mosquito Swarm", deadly_distance=1),
        OholObject(1323, "Wild Boar", deadly_distance=1),
        OholObject(421, "Dead Wolf with Arrow", deadly_distance=0),
    )
    nearby = (
        ObjectState(2156, "Mosquito Swarm", Tile(1, 0)),
        ObjectState(1323, "Wild Boar", Tile(2, 0)),
        ObjectState(421, "Dead Wolf with Arrow", Tile(3, 0)),
    )

    assert dangerous_tiles(nearby, game_data) == frozenset({Tile(1, 0), Tile(2, 0)})


def test_dangerous_tiles_falls_back_to_name_matching_without_game_data() -> None:
    nearby = (
        ObjectState(1, "Mosquito Swarm", Tile(1, 0)),
        ObjectState(2, "Attacking Wild Boar", Tile(2, 0)),
        ObjectState(3, "Berry", Tile(0, 0), food_value=3),
    )

    assert dangerous_tiles(nearby) == frozenset({Tile(1, 0), Tile(2, 0)})


def test_dangerous_objects_preview_lists_nearby_threats() -> None:
    nearby = (
        ObjectState(1, "Wild Boar", Tile(4, 1)),
        ObjectState(2, "Round Stone", Tile(0, 0)),
    )

    preview = dangerous_objects_preview(nearby)

    assert preview == ({"x": 4, "y": 1, "name": "Wild Boar"},)


def test_is_dangerous_object_detects_attacking_rattle_snake_with_game_data() -> None:
    game_data = _game_data(
        OholObject(1385, "Attacking Rattle Snake", deadly_distance=0),
        OholObject(764, "Rattle Snake", deadly_distance=1),
        OholObject(765, "Snake Skin", deadly_distance=0),
    )
    nearby = (
        ObjectState(1385, "Attacking Rattle Snake", Tile(1, 0)),
        ObjectState(764, "Rattle Snake", Tile(2, 0)),
        ObjectState(765, "Snake Skin", Tile(3, 0)),
    )

    assert dangerous_tiles(nearby, game_data) == frozenset({Tile(1, 0), Tile(2, 0)})


def test_danger_path_blockers_expands_chebyshev_buffer() -> None:
    blocked = danger_path_blockers((Tile(0, 0),), buffer=1)

    assert Tile(0, 0) in blocked
    assert Tile(1, 0) in blocked
    assert Tile(0, 1) in blocked
    assert Tile(2, 0) not in blocked


def test_danger_near_route_detects_corridor_threats() -> None:
    danger = {Tile(3, 0)}
    assert danger_near_route(Tile(0, 0), Tile(6, 0), danger)
    assert not danger_near_route(Tile(0, 0), Tile(6, 0), {Tile(0, 8)})


def test_dangerous_name_phrases_cover_mosquito_boar_and_snake() -> None:
    assert "mosquito swarm" in DANGEROUS_NAME_PHRASES
    assert "wild boar" in DANGEROUS_NAME_PHRASES
    assert "rattle snake" in DANGEROUS_NAME_PHRASES
