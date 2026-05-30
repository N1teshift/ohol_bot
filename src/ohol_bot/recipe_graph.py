from __future__ import annotations

from dataclasses import dataclass

from .game_data import OholGameData, OholTransition


@dataclass(frozen=True, slots=True)
class RecipeEdge:
    actor_id: int
    target_id: int
    output_id: int


def direct_recipe_edges_for_output(
    game_data: OholGameData,
    output_id: int,
) -> tuple[RecipeEdge, ...]:
    """Return one-step transitions that can produce output_id.

    Includes transitions where output appears as either new actor or new target.
    """
    edges: list[RecipeEdge] = []
    for transition in game_data.transitions:
        _append_if_output(edges, transition, output_id)
    return tuple(edges)


def direct_recipe_input_names_for_output(
    game_data: OholGameData,
    output_id: int,
) -> frozenset[str]:
    names: set[str] = set()
    for edge in direct_recipe_edges_for_output(game_data, output_id):
        if edge.actor_id > 0:
            names.add(game_data.object_name(edge.actor_id).lower())
        if edge.target_id > 0:
            names.add(game_data.object_name(edge.target_id).lower())
    return frozenset(names)


def _append_if_output(edges: list[RecipeEdge], transition: OholTransition, output_id: int) -> None:
    if transition.new_actor_id == output_id:
        edges.append(
            RecipeEdge(
                actor_id=transition.actor_id,
                target_id=transition.target_id,
                output_id=output_id,
            )
        )
    if transition.new_target_id == output_id:
        edges.append(
            RecipeEdge(
                actor_id=transition.actor_id,
                target_id=transition.target_id,
                output_id=output_id,
            )
        )
