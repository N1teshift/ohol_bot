from ohol_bot.model import Observation, PlayerState, Tile
from ohol_bot.planner_facts import planner_facts


def _obs(facts: dict) -> Observation:
    return Observation(
        tick=1,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=20.0,
            food_store=10,
            max_food_store=20,
        ),
        facts=facts,
    )


def test_planner_facts_parses_tiles_and_previous() -> None:
    facts = planner_facts(
        _obs(
            {
                "avoid_targets": ((1, 2),),
                "blocked_tiles": ((-1, 0),),
                "previous_tile": {"x": 0, "y": 1},
            }
        )
    )

    assert Tile(1, 2) in facts.avoid_targets
    assert Tile(-1, 0) in facts.blocked_tiles
    assert facts.previous_tile == Tile(0, 1)


def test_planner_facts_parses_remembered_targets() -> None:
    facts = planner_facts(
        _obs(
            {
                "nearest_remembered_food": {
                    "name": "gooseberry",
                    "rel_x": 4,
                    "rel_y": -2,
                    "distance": 6,
                },
                "nearest_remembered_collect": {
                    "name": "Maple Tree",
                    "rel_x": 9,
                    "rel_y": 1,
                },
            }
        )
    )

    assert facts.nearest_remembered_food is not None
    assert facts.nearest_remembered_food.name == "gooseberry"
    assert facts.nearest_remembered_food.tile == Tile(4, -2)
    assert facts.nearest_remembered_food.distance == 6
    assert facts.nearest_remembered_collect is not None
    assert facts.nearest_remembered_collect.tile == Tile(9, 1)
