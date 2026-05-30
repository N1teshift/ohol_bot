from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .model import Tile


class FamilyRole(str, Enum):
    MOTHER = "mother"
    CARETAKER = "caretaker"
    FARMER = "farmer"
    FORAGER = "forager"
    TOOLMAKER = "toolmaker"
    EXPLORER = "explorer"


@dataclass(slots=True)
class SharedMemory:
    home: Tile | None = None
    food_tiles: set[Tile] = field(default_factory=set)
    danger_tiles: set[Tile] = field(default_factory=set)
    missing_resources: set[str] = field(default_factory=set)
    babies_needing_care: set[int] = field(default_factory=set)
    current_goals: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BotAssignment:
    player_id: int
    role: FamilyRole
    goal: str


class FamilyCoordinator:
    def __init__(self, memory: SharedMemory | None = None) -> None:
        self.memory = memory or SharedMemory()

    def assign_roles(self, player_ids: list[int]) -> tuple[BotAssignment, ...]:
        role_order = [
            FamilyRole.MOTHER,
            FamilyRole.CARETAKER,
            FamilyRole.FARMER,
            FamilyRole.FORAGER,
            FamilyRole.TOOLMAKER,
            FamilyRole.EXPLORER,
        ]
        assignments: list[BotAssignment] = []
        for index, player_id in enumerate(player_ids):
            role = role_order[index % len(role_order)]
            assignment = BotAssignment(
                player_id=player_id,
                role=role,
                goal=_default_goal(role),
            )
            self.memory.current_goals[player_id] = assignment.goal
            assignments.append(assignment)
        return tuple(assignments)

    def family_metrics(self) -> dict[str, float]:
        return {
            "known_food_tiles": float(len(self.memory.food_tiles)),
            "known_danger_tiles": float(len(self.memory.danger_tiles)),
            "babies_needing_care": float(len(self.memory.babies_needing_care)),
            "missing_resource_count": float(len(self.memory.missing_resources)),
            "assigned_bot_count": float(len(self.memory.current_goals)),
        }


def _default_goal(role: FamilyRole) -> str:
    if role is FamilyRole.MOTHER:
        return "stay fed and keep fertile lineage alive"
    if role is FamilyRole.CARETAKER:
        return "feed babies and monitor home food"
    if role is FamilyRole.FARMER:
        return "maintain renewable food"
    if role is FamilyRole.FORAGER:
        return "bring wild food and early resources home"
    if role is FamilyRole.TOOLMAKER:
        return "produce tools needed by farmers and cooks"
    return "map nearby resources and dangers"
