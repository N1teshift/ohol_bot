from __future__ import annotations

from abc import ABC, abstractmethod

from .model import Action, ActionType, Observation
from .home import is_at_home


class Policy(ABC):
    @abstractmethod
    def decide(self, observation: Observation) -> Action:
        raise NotImplementedError


class SurvivalPolicy(Policy):
    """Simple baseline: eat when hungry, otherwise stay near useful context."""

    def __init__(self, hunger_threshold: float = 0.45) -> None:
        self.hunger_threshold = hunger_threshold

    def decide(self, observation: Observation) -> Action:
        player = observation.self

        if player.hunger_ratio <= self.hunger_threshold:
            food = observation.nearest_food()
            if food is not None:
                if player.tile == food.tile:
                    return Action(ActionType.USE, {"held_item": player.held_object_id, "target_x": food.tile.x, "target_y": food.tile.y})
                return Action(ActionType.MOVE_TO, {"x": food.tile.x, "y": food.tile.y})

        if observation.home is not None and not is_at_home(observation, player.tile):
            return Action(ActionType.MOVE_TO, {"x": observation.home.x, "y": observation.home.y})

        return Action(ActionType.WAIT, {"ticks": 1})
