from ohol_bot.behaviors import RecipeBehavior, SurvivalBehavior
from ohol_bot.game_data import OholGameData, OholObject, OholTransition
from ohol_bot.model import ActionType, ObjectState, Observation, PlayerState, Tile


def _observation(*, nearby_objects=(), food_store: int = 20) -> Observation:
    return Observation(
        tick=1,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=20.0,
            food_store=food_store,
            max_food_store=20,
            is_stationary=True,
        ),
        nearby_objects=nearby_objects,
        home=Tile(0, 0),
    )


def test_recipe_behavior_disabled_by_default() -> None:
    behavior = RecipeBehavior()
    observation = _observation(
        nearby_objects=(
            ObjectState(object_id=1, name="Sharp Stone", tile=Tile(2, 0)),
        )
    )

    assert behavior.decide(observation) is None


def test_recipe_behavior_moves_to_recipe_resource_when_enabled() -> None:
    behavior = RecipeBehavior(enabled=True)
    observation = _observation(
        nearby_objects=(
            ObjectState(object_id=1, name="Sharp Stone", tile=Tile(2, 0)),
        )
    )

    result = behavior.decide(observation)

    assert result is not None
    assert result.action.type is ActionType.MOVE_TO
    assert result.action.payload == {"x": 2, "y": 0}


def test_survival_behavior_still_waits_when_full_and_idle() -> None:
    behavior = SurvivalBehavior()
    result = behavior.decide(_observation())

    assert result is not None
    assert result.action.type is ActionType.WAIT


def test_recipe_behavior_resources_for_goal_from_transitions() -> None:
    from ohol_bot.biomes import BiomeCatalog

    data = OholGameData(
        objects={
            1: OholObject(object_id=1, name="Sharp Stone"),
            2: OholObject(object_id=2, name="Branch"),
            99: OholObject(object_id=99, name="Axe"),
        },
        transitions=(
            OholTransition(actor_id=1, target_id=2, new_actor_id=99, new_target_id=0),
        ),
        biomes=BiomeCatalog({}),
    )

    names = RecipeBehavior.resources_for_goal(data, output_id=99)

    assert names == frozenset({"sharp stone", "branch"})
