from argparse import Namespace

from ohol_bot.behaviors import RecipeBehavior
from ohol_bot.biomes import BiomeCatalog
from ohol_bot.cli import _build_run_live_planner
from ohol_bot.game_data import OholGameData, OholObject, OholTransition
from ohol_bot.protocol_client import OholProtocolClient


def test_build_run_live_planner_recipe_disabled_by_default() -> None:
    args = Namespace(enable_recipe_behavior=False, recipe_goal_object_id=None)
    client = OholProtocolClient()

    planner = _build_run_live_planner(args, client)

    first = planner.behaviors[0]
    assert isinstance(first, RecipeBehavior)
    assert first.enabled is False


def test_build_run_live_planner_uses_goal_inputs_when_available() -> None:
    args = Namespace(enable_recipe_behavior=True, recipe_goal_object_id=99)
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
    client = OholProtocolClient(game_data=data)

    planner = _build_run_live_planner(args, client)

    first = planner.behaviors[0]
    assert isinstance(first, RecipeBehavior)
    assert first.enabled is True
    assert first.resource_names == frozenset({"sharp stone", "branch"})
