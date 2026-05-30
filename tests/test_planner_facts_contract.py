from ohol_bot.model import ActionType, Observation, PlayerState, Tile
from ohol_bot.planner import SurvivalPlanner
from ohol_bot.skills import SkillLibrary


def _player(*, tile: Tile = Tile(0, 0), food_store: int = 10) -> PlayerState:
    return PlayerState(
        player_id=1,
        tile=tile,
        age=20.0,
        food_store=food_store,
        max_food_store=20,
        is_stationary=True,
    )


def test_forage_ignores_avoid_target_food_tile() -> None:
    skills = SkillLibrary()
    observation = Observation(
        tick=1,
        self=_player(food_store=19),
        nearby_objects=(),
        facts={
            "nearest_remembered_food": {
                "name": "gooseberry",
                "rel_x": 3,
                "rel_y": 0,
                "distance": 3,
            },
            "avoid_targets": ((3, 0),),
        },
    )

    result = skills.forage_food(observation)

    assert result is None


def test_explore_step_skips_previous_tile_from_facts() -> None:
    planner = SurvivalPlanner()
    observation = Observation(
        tick=0,
        self=_player(food_store=19),
        facts={
            "previous_tile": {"x": 0, "y": 1},
        },
    )

    action = planner.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload != {"x": 0, "y": 1}


def test_explore_step_uses_blocked_and_avoid_tuples() -> None:
    planner = SurvivalPlanner()
    observation = Observation(
        tick=0,
        self=_player(food_store=19),
        facts={
            "blocked_tiles": ((0, 1),),
            "avoid_targets": ((1, 0),),
            "previous_tile": {"x": 0, "y": -1},
        },
    )

    action = planner.decide(observation)

    assert action.type is ActionType.MOVE_TO
    chosen = (action.payload["x"], action.payload["y"])
    assert chosen not in {(0, 1), (1, 0), (0, -1)}


def test_collect_moves_to_remembered_collect_fact() -> None:
    skills = SkillLibrary()
    observation = Observation(
        tick=1,
        self=_player(food_store=20),
        facts={
            "nearest_remembered_collect": {
                "name": "Maple Tree",
                "rel_x": -2,
                "rel_y": 4,
                "distance": 6,
            }
        },
    )

    result = skills.collect_named_object(observation, {"straight branch", "curved branch"})

    assert result is not None
    assert result.action.type is ActionType.MOVE_TO
    assert result.action.payload == {"x": -2, "y": 4}
