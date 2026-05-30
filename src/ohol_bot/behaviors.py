from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import Action, ActionType, Observation
from .skills import SkillLibrary, _explore_step


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
    """Scaffold for future recipe/transition planning behavior."""

    def decide(self, observation: Observation) -> BehaviorResult | None:
        _ = observation
        return None
