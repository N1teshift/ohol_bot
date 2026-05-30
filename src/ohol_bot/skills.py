from __future__ import annotations



from dataclasses import dataclass



from .hunger import eat_blocker

from .model import Action, ActionType, Observation, ObjectState, Tile


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

        food = observation.nearest_food(exclude=_avoid_targets(observation))

        if food is None:

            return None

        if food.tile in _avoid_targets(observation):

            return None



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



    def return_home(self, observation: Observation, max_distance: int = 12) -> SkillResult | None:

        if observation.home is None:

            return None

        player = observation.self

        if player.tile.distance_to(observation.home) <= max_distance:

            return None

        return SkillResult(

            name="return_home",

            action=Action(ActionType.MOVE_TO, {"x": observation.home.x, "y": observation.home.y}),

            reason="too far from home",

        )



    def collect_named_object(self, observation: Observation, names: set[str]) -> SkillResult | None:

        target = _nearest_named_object(observation, names)

        if target is None:

            return None

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


def _avoid_targets(observation: Observation) -> frozenset[Tile]:
    raw = observation.facts.get("avoid_targets")
    if not isinstance(raw, tuple):
        return frozenset()
    return frozenset(Tile(int(x), int(y)) for x, y in raw)


def _blocked_tiles(observation: Observation) -> frozenset[Tile]:
    raw = observation.facts.get("blocked_tiles")
    if not isinstance(raw, tuple):
        return frozenset()
    return frozenset(Tile(int(x), int(y)) for x, y in raw)


def _explore_step(observation: Observation) -> Tile:
    player = observation.self
    blocked = _blocked_tiles(observation) | _avoid_targets(observation)
    previous = _previous_tile(observation)
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


def _previous_tile(observation: Observation) -> Tile | None:
    raw = observation.facts.get("previous_tile")
    if not isinstance(raw, dict):
        return None
    return Tile(int(raw["x"]), int(raw["y"]))

