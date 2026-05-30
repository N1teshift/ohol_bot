from __future__ import annotations

from .model import Action, ActionType, Observation, Tile
from .skills import SkillLibrary, _avoid_targets, _explore_step


class SurvivalPlanner:
    def __init__(self, skills: SkillLibrary | None = None) -> None:
        self.skills = skills or SkillLibrary()

    def decide(self, observation: Observation) -> Action:
        if observation.self.is_being_carried:
            return Action(ActionType.WAIT, {"ticks": 1})

        from .hunger import action_blocker

        if action_blocker(observation) is not None:
            return Action(ActionType.WAIT, {"ticks": 1})

        if observation.self.is_hungry:
            forage = self.skills.forage_food(observation)
            if forage is not None:
                return forage.action

            explore = _explore_step(observation)
            return Action(ActionType.MOVE_TO, {"x": explore.x, "y": explore.y})

        return_home = self.skills.return_home(observation)
        if return_home is not None:
            return return_home.action

        collect_branch = self.skills.collect_named_object(
            observation, {"straight branch", "curved branch"}
        )
        if collect_branch is not None and observation.self.held_object_id is None:
            return collect_branch.action

        return Action(ActionType.WAIT, {"ticks": 1})
