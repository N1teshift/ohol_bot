from __future__ import annotations

from abc import ABC, abstractmethod

from .model import Action, ActionType, Observation, Tile


class BotClient(ABC):
    """Small, legal-action interface used by scripted and learned policies."""

    @abstractmethod
    def observe(self) -> Observation:
        raise NotImplementedError

    @abstractmethod
    def send(self, action: Action) -> None:
        raise NotImplementedError

    def move_to(self, tile: Tile) -> None:
        self.send(Action(ActionType.MOVE_TO, {"x": tile.x, "y": tile.y}))

    def pick_up(self, tile: Tile) -> None:
        self.send(Action(ActionType.PICK_UP, {"x": tile.x, "y": tile.y}))

    def use(self, held_item: int | None, target: Tile) -> None:
        self.send(
            Action(
                ActionType.USE,
                {"held_item": held_item, "target_x": target.x, "target_y": target.y},
            )
        )

    def use_self(self, tile: Tile) -> None:
        self.send(Action(ActionType.USE_SELF, {"x": tile.x, "y": tile.y}))

    def drop(self, tile: Tile) -> None:
        self.send(Action(ActionType.DROP, {"x": tile.x, "y": tile.y}))

    def say(self, text: str) -> None:
        self.send(Action(ActionType.SAY, {"text": text}))

    def force(self, tile: Tile) -> None:
        self.send(Action(ActionType.FORCE, {"x": tile.x, "y": tile.y}))

    def wait(self, ticks: int = 1) -> None:
        self.send(Action(ActionType.WAIT, {"ticks": ticks}))


class MockBotClient(BotClient):
    """Test driver until a real OHOL protocol bridge is implemented."""

    def __init__(self, observations: list[Observation]) -> None:
        if not observations:
            raise ValueError("MockBotClient requires at least one observation")
        self._observations = observations
        self._index = 0
        self.actions: list[Action] = []

    def observe(self) -> Observation:
        obs = self._observations[min(self._index, len(self._observations) - 1)]
        self._index += 1
        return obs

    def send(self, action: Action) -> None:
        self.actions.append(action)
