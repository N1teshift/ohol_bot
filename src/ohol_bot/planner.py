from __future__ import annotations

from .behaviors import Behavior, RecipeBehavior, SurvivalBehavior
from .model import Action, ActionType, Observation
from .skills import SkillLibrary


class SurvivalPlanner:
    def __init__(
        self,
        skills: SkillLibrary | None = None,
        behaviors: tuple[Behavior, ...] | None = None,
        *,
        enable_recipe_behavior: bool = False,
        recipe_resource_names: frozenset[str] | None = None,
    ) -> None:
        self.skills = skills or SkillLibrary()
        self.behaviors = behaviors or (
            RecipeBehavior(enabled=enable_recipe_behavior),
            SurvivalBehavior(self.skills),
        )
        if behaviors is None and recipe_resource_names is not None:
            self.behaviors = (
                RecipeBehavior(
                    enabled=enable_recipe_behavior,
                    resource_names=recipe_resource_names,
                ),
                SurvivalBehavior(self.skills),
            )

    def decide(self, observation: Observation) -> Action:
        if observation.self.is_being_carried:
            return Action(ActionType.WAIT, {"ticks": 1})

        from .hunger import action_blocker

        if action_blocker(observation) is not None:
            return Action(ActionType.WAIT, {"ticks": 1})

        for behavior in self.behaviors:
            result = behavior.decide(observation)
            if result is not None:
                return result.action

        return Action(ActionType.WAIT, {"ticks": 1})
