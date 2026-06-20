from __future__ import annotations



from dataclasses import dataclass



from .hunger import eat_blocker
from .planner_facts import PlannerFacts, planner_facts

from .model import Action, ActionType, Observation, ObjectState, Tile
from .home import home_area_radius, is_at_home


@dataclass(frozen=True, slots=True)

class SkillResult:

    name: str

    action: Action

    reason: str





class SkillLibrary:

    def forage_food(self, observation: Observation) -> SkillResult | None:

        player = observation.self



        if player.is_holding_food:

            blocked = eat_blocker(observation)

            if blocked is not None:

                return SkillResult(

                    name="forage_food",

                    action=Action(ActionType.WAIT, {"ticks": 1}),

                    reason=blocked,

                )

            food_name = player.held_object_name or "food"

            return SkillResult(

                name="forage_food",

                action=Action(

                    ActionType.USE_SELF,

                    {"x": player.tile.x, "y": player.tile.y},

                ),

                reason=f"eat held {food_name}",

            )

        if player.held_object_id is not None:

            return SkillResult(

                name="forage_food",

                action=Action(

                    ActionType.DROP,

                    {"x": player.tile.x, "y": player.tile.y},

                ),

                reason="drop held item to pick up food",

            )

        adjacent = _adjacent_food(observation)

        if adjacent is not None:

            return SkillResult(

                name="forage_food",

                action=Action(

                    ActionType.PICK_UP,

                    {"x": adjacent.tile.x, "y": adjacent.tile.y},

                ),

                reason=f"pick up {adjacent.name}",

            )

        facts = planner_facts(observation)
        food = observation.nearest_food(exclude=facts.avoid_targets)

        if food is not None and food.tile not in facts.avoid_targets:
            if player.tile == food.tile or _is_adjacent(player.tile, food.tile):
                return SkillResult(
                    name="forage_food",
                    action=Action(
                        ActionType.PICK_UP,
                        {"x": food.tile.x, "y": food.tile.y},
                    ),
                    reason=f"pick up {food.name}",
                )
            return SkillResult(
                name="forage_food",
                action=Action(ActionType.MOVE_TO, {"x": food.tile.x, "y": food.tile.y}),
                reason=f"move to food {food.name}",
            )

        remembered = _move_toward_remembered(
            observation,
            facts,
            fact_key="nearest_remembered_food",
            pickup_when_reached=True,
        )
        if remembered is not None:
            return remembered

        return None



    def return_home(self, observation: Observation, max_distance: int | None = None) -> SkillResult | None:

        if observation.home is None:

            return None

        player = observation.self

        radius = max_distance if max_distance is not None else home_area_radius(observation)

        if is_at_home(observation, player.tile, radius=radius):

            return None

        return SkillResult(

            name="return_home",

            action=Action(ActionType.MOVE_TO, {"x": observation.home.x, "y": observation.home.y}),

            reason="too far from home",

        )



    def collect_named_object(self, observation: Observation, names: set[str]) -> SkillResult | None:

        target = _nearest_named_object(observation, names)

        if target is not None:
            if observation.self.tile == target.tile:
                return SkillResult(
                    name="collect_named_object",
                    action=Action(ActionType.PICK_UP, {"x": target.tile.x, "y": target.tile.y}),
                    reason=f"pick up {target.name}",
                )
            return SkillResult(
                name="collect_named_object",
                action=Action(ActionType.MOVE_TO, {"x": target.tile.x, "y": target.tile.y}),
                reason=f"move to {target.name}",
            )

        remembered = _move_toward_remembered(
            observation,
            planner_facts(observation),
            fact_key="nearest_remembered_collect",
            pickup_when_reached=True,
        )
        if remembered is not None:
            return remembered

        return None





def _nearest_named_object(observation: Observation, names: set[str]) -> ObjectState | None:

    candidates = [obj for obj in observation.nearby_objects if obj.name in names]

    if not candidates:

        return None

    return min(candidates, key=lambda obj: observation.self.tile.distance_to(obj.tile))


def _is_adjacent(a: Tile, b: Tile) -> bool:
    return max(abs(a.x - b.x), abs(a.y - b.y)) == 1


def _adjacent_food(observation: Observation) -> ObjectState | None:
    candidates = [
        obj
        for obj in observation.nearby_objects
        if obj.food_value > 0 and _is_adjacent(observation.self.tile, obj.tile)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda obj: observation.self.tile.distance_to(obj.tile),
    )


def _explore_step(observation: Observation) -> Tile:
    player = observation.self
    facts = planner_facts(observation)
    blocked = facts.blocked_tiles | facts.avoid_targets
    previous = facts.previous_tile
    offsets = (
        (0, 1),
        (1, 0),
        (0, -1),
        (-1, 0),
        (1, 1),
        (-1, 1),
        (1, -1),
        (-1, -1),
    )
    start = observation.tick % len(offsets)
    rotated = offsets[start:] + offsets[:start]
    for dx, dy in rotated:
        step = Tile(player.tile.x + dx, player.tile.y + dy)
        if step in blocked or step == previous:
            continue
        return step
    for dx, dy in rotated:
        step = Tile(player.tile.x + dx, player.tile.y + dy)
        if step not in blocked:
            return step
    return Tile(player.tile.x + 1, player.tile.y)


def _move_toward_remembered(
    observation: Observation,
    facts: PlannerFacts,
    *,
    fact_key: str,
    pickup_when_reached: bool = False,
) -> SkillResult | None:
    remembered = (
        facts.nearest_remembered_food
        if fact_key == "nearest_remembered_food"
        else facts.nearest_remembered_collect
    )
    if remembered is None:
        return None
    target = remembered.tile
    if target in facts.avoid_targets:
        return None
    player = observation.self
    at_target = player.tile == target
    adjacent = _is_adjacent(player.tile, target)
    if pickup_when_reached and (at_target or adjacent):
        return SkillResult(
            name="navigate_remembered",
            action=Action(ActionType.PICK_UP, {"x": target.x, "y": target.y}),
            reason=f"remembered {remembered.name} (pick up)",
        )
    return SkillResult(
        name="navigate_remembered",
        action=Action(ActionType.MOVE_TO, {"x": target.x, "y": target.y}),
        reason=f"remembered {remembered.name}",
    )

