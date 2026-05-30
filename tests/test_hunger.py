from ohol_bot.hunger import HUNGER_MISSING_PIPS_THRESHOLD, is_planner_hungry
from ohol_bot.model import PlayerState, Tile


def test_planner_hungry_with_one_missing_pip() -> None:
    player = PlayerState(
        player_id=1,
        tile=Tile(0, 0),
        age=18,
        food_store=19,
        max_food_store=20,
    )

    assert player.missing_food_pips == 1
    assert is_planner_hungry(player) is True


def test_planner_not_hungry_when_full() -> None:
    player = PlayerState(
        player_id=1,
        tile=Tile(0, 0),
        age=18,
        food_store=20,
        max_food_store=20,
    )

    assert is_planner_hungry(player) is False


def test_seventeen_of_twenty_is_hungry() -> None:
    player = PlayerState(
        player_id=1,
        tile=Tile(0, 0),
        age=18,
        food_store=17,
        max_food_store=20,
    )

    assert player.missing_food_pips == 3
    assert is_planner_hungry(player) is True
    assert HUNGER_MISSING_PIPS_THRESHOLD == 1
