from ohol_bot.model import Tile
from ohol_bot.tiles import (
    chebyshev,
    danger_tiles,
    is_adjacent,
    is_adjacent_or_same,
    is_orthogonally_adjacent,
    tile_frozenset_from_facts,
    tile_from_fact,
    tile_sequence_from_facts,
    tile_set_from_facts,
)


def test_chebyshev_diagonal_is_one() -> None:
    assert chebyshev(Tile(0, 0), Tile(1, 1)) == 1


def test_chebyshev_same_tile_is_zero() -> None:
    assert chebyshev(Tile(3, 4), Tile(3, 4)) == 0


def test_is_adjacent_requires_chebyshev_one() -> None:
    assert is_adjacent(Tile(0, 0), Tile(1, 0))
    assert not is_adjacent(Tile(0, 0), Tile(2, 0))
    assert not is_adjacent(Tile(0, 0), Tile(0, 0))


def test_is_adjacent_or_same_includes_same_tile() -> None:
    assert is_adjacent_or_same(Tile(0, 0), Tile(0, 0))
    assert is_adjacent_or_same(Tile(0, 0), Tile(1, 1))
    assert not is_adjacent_or_same(Tile(0, 0), Tile(2, 0))


def test_is_orthogonally_adjacent_excludes_diagonal() -> None:
    assert is_orthogonally_adjacent(Tile(0, 0), Tile(1, 0))
    assert not is_orthogonally_adjacent(Tile(0, 0), Tile(1, 1))


def test_tile_from_fact_accepts_dict_and_pairs() -> None:
    assert tile_from_fact({"x": 2, "y": 3}) == Tile(2, 3)
    assert tile_from_fact((4, 5)) == Tile(4, 5)
    assert tile_from_fact("bad") is None


def test_tile_set_from_facts_parses_tuple_pairs() -> None:
    assert tile_set_from_facts(((1, 2), (3, 4))) == {Tile(1, 2), Tile(3, 4)}


def test_tile_frozenset_from_facts_parses_mixed_entries() -> None:
    raw = ({"x": 1, "y": 2}, (3, 4))
    assert tile_frozenset_from_facts(raw) == frozenset({Tile(1, 2), Tile(3, 4)})


def test_tile_sequence_from_facts_preserves_order() -> None:
    assert tile_sequence_from_facts(((1, 0), (2, 0))) == (Tile(1, 0), Tile(2, 0))


def test_danger_tiles_merges_avoid_and_danger() -> None:
    from ohol_bot.model import Observation, PlayerState

    observation = Observation(
        tick=1,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=20.0,
            food_store=20,
            max_food_store=20,
        ),
        facts={
            "avoid_targets": ((1, 0),),
            "danger_tiles": ((0, 1),),
        },
    )
    assert danger_tiles(observation) == {Tile(1, 0), Tile(0, 1)}
