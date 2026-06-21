from ohol_bot.model import ActionType, Observation, PlayerState, Tile
from ohol_bot.skills import SkillLibrary


def _observation_with_remembered(
    *,
    food_fact: dict | None = None,
    collect_fact: dict | None = None,
) -> Observation:
    facts: dict = {}
    if food_fact is not None:
        facts["nearest_remembered_food"] = food_fact
    if collect_fact is not None:
        facts["nearest_remembered_collect"] = collect_fact
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


def test_forage_moves_toward_remembered_food() -> None:
    skills = SkillLibrary()
    observation = _observation_with_remembered(
        food_fact={
            "name": "gooseberry",
            "rel_x": 5,
            "rel_y": 0,
            "distance": 5,
        },
    )

    result = skills.forage_food(observation)

    assert result is not None
    assert result.action.type is ActionType.MOVE_TO
    assert result.action.payload == {"x": 4, "y": 0}
    assert "remembered gooseberry" in result.reason


def test_forage_picks_up_adjacent_remembered_food() -> None:
    skills = SkillLibrary()
    observation = _observation_with_remembered(
        food_fact={
            "name": "gooseberry",
            "rel_x": 1,
            "rel_y": 0,
            "distance": 1,
        },
    )

    result = skills.forage_food(observation)

    assert result is not None
    assert result.action.type is ActionType.PICK_UP
    assert result.action.payload == {"x": 1, "y": 0}


def test_collect_moves_toward_remembered_tree() -> None:
    skills = SkillLibrary()
    observation = _observation_with_remembered(
        collect_fact={
            "name": "Maple Tree",
            "rel_x": 0,
            "rel_y": 8,
            "distance": 8,
        },
    )

    result = skills.collect_named_object(
        observation, {"straight branch", "curved branch"}
    )

    assert result is not None
    assert result.action.type is ActionType.MOVE_TO
    assert result.action.payload == {"x": 0, "y": 7}
    assert "remembered Maple Tree" in result.reason
