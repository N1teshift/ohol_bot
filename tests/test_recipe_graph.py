from ohol_bot.game_data import OholGameData, OholObject, OholTransition
from ohol_bot.recipe_graph import (
    direct_recipe_edges_for_output,
    direct_recipe_input_names_for_output,
)


def _game_data() -> OholGameData:
    from ohol_bot.biomes import BiomeCatalog

    return OholGameData(
        objects={
            1: OholObject(object_id=1, name="Sharp Stone"),
            2: OholObject(object_id=2, name="Round Stone"),
            3: OholObject(object_id=3, name="Branch"),
            10: OholObject(object_id=10, name="Hatchet"),
        },
        transitions=(
            OholTransition(actor_id=1, target_id=3, new_actor_id=10, new_target_id=0),
            OholTransition(actor_id=2, target_id=3, new_actor_id=0, new_target_id=10),
        ),
        biomes=BiomeCatalog({}),
    )


def test_direct_recipe_edges_for_output_matches_actor_and_target() -> None:
    data = _game_data()

    edges = direct_recipe_edges_for_output(data, output_id=10)

    assert len(edges) == 2
    assert {edge.actor_id for edge in edges} == {1, 2}


def test_direct_recipe_input_names_for_output_returns_lower_names() -> None:
    data = _game_data()

    names = direct_recipe_input_names_for_output(data, output_id=10)

    assert names == frozenset({"sharp stone", "round stone", "branch"})
