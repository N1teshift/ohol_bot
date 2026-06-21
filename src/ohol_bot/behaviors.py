from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .game_data import OholGameData
from .model import Action, ActionType, Observation
from .recipe_graph import direct_recipe_input_names_for_output
from .skills import SkillLibrary, _explore_step
from .spatial_queries import nearest_object
from .tiles import is_adjacent


@dataclass(frozen=True, slots=True)
class BehaviorResult:
    action: Action
    reason: str


class Behavior(Protocol):
    def decide(self, observation: Observation) -> BehaviorResult | None:
        ...


class SurvivalBehavior:
    """Current single-bot survival behavior."""

    def __init__(self, skills: SkillLibrary | None = None) -> None:
        self.skills = skills or SkillLibrary()

    def decide(self, observation: Observation) -> BehaviorResult | None:
        if observation.self.is_hungry:
            forage = self.skills.forage_food(observation)
            if forage is not None:
                return BehaviorResult(action=forage.action, reason=forage.reason)
            explore = _explore_step(observation)
            return BehaviorResult(
                action=Action(ActionType.MOVE_TO, {"x": explore.x, "y": explore.y}),
                reason="hungry and no food target, explore",
            )

        return_home = self.skills.return_home(observation)
        if return_home is not None:
            return BehaviorResult(action=return_home.action, reason=return_home.reason)

        collect_branch = self.skills.collect_named_object(
            observation, {"straight branch", "curved branch"}
        )
        if collect_branch is not None and observation.self.held_object_id is None:
            return BehaviorResult(action=collect_branch.action, reason=collect_branch.reason)

        return BehaviorResult(
            action=Action(ActionType.WAIT, {"ticks": 1}),
            reason="no active survival objective",
        )


class RecipeBehavior:
    """Small opt-in recipe behavior for early resource gathering."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        resource_names: frozenset[str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.resource_names = resource_names or frozenset(
            {"sharp stone", "round stone", "straight branch", "curved branch"}
        )

    @staticmethod
    def resources_for_goal(
        game_data: OholGameData,
        output_id: int,
    ) -> frozenset[str]:
        inputs = direct_recipe_input_names_for_output(game_data, output_id)
        if inputs:
            return inputs
        return frozenset({"sharp stone", "round stone", "straight branch", "curved branch"})

    def decide(self, observation: Observation) -> BehaviorResult | None:
        if not self.enabled:
            return None

        player = observation.self
        if player.held_object_id is not None:
            return None

        target = nearest_object(
            observation,
            names=self.resource_names,
            normalize_names=True,
        )
        if target is None:
            return None

        if player.tile == target.tile or is_adjacent(player.tile, target.tile):
            return BehaviorResult(
                action=Action(ActionType.PICK_UP, {"x": target.tile.x, "y": target.tile.y}),
                reason=f"recipe gather {target.name}",
            )

        return BehaviorResult(
            action=Action(ActionType.MOVE_TO, {"x": target.tile.x, "y": target.tile.y}),
            reason=f"recipe move to {target.name}",
        )
