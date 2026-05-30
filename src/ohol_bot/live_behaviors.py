from __future__ import annotations

import time
from dataclasses import dataclass

from .model import Action, ActionType, Observation, Tile
from .protocol_client import OholProtocolClient


@dataclass(frozen=True, slots=True)
class LiveBehaviorReport:
    self_player_id: int | None
    initial_tile: Tile
    final_tile: Tile
    say_sent: bool
    move_sent: bool
    eat_attempted: bool
    hunger_ratio: float
    tracked_objects: int
    nearby_food: tuple[dict[str, object], ...]
    checks: dict[str, bool]
    actions: tuple[dict[str, object], ...]


def verify_live_behaviors(
    client: OholProtocolClient,
    *,
    settle_seconds: float = 5.0,
    action_pause_seconds: float = 1.5,
) -> LiveBehaviorReport:
    if not client.logged_in:
        client.login()

    client.poll_until(settle_seconds)
    initial = client.observe()
    actions: list[dict[str, object]] = []

    client.say("BOT_CHECK")
    actions.append({"type": "say", "text": "BOT_CHECK"})
    client.poll_until(action_pause_seconds)

    moved_to = Tile(initial.self.tile.x + 1, initial.self.tile.y)
    client.move_to(moved_to)
    actions.append({"type": "move_to", "x": moved_to.x, "y": moved_to.y})
    client.poll_until(action_pause_seconds)

    after_move = client.observe()
    eat_attempted = False
    food = after_move.nearest_food()
    if food is not None:
        if after_move.self.tile != food.tile:
            client.move_to(food.tile)
            actions.append({"type": "move_to", "x": food.tile.x, "y": food.tile.y})
            client.poll_until(action_pause_seconds)
            after_move = client.observe()

        if after_move.self.tile == food.tile:
            client.use(after_move.self.held_object_id, food.tile)
            actions.append(
                {
                    "type": "use",
                    "target_x": food.tile.x,
                    "target_y": food.tile.y,
                    "object_id": food.object_id,
                    "object_name": food.name,
                }
            )
            eat_attempted = True
            client.poll_until(action_pause_seconds)

    final = client.observe()
    nearby_food = tuple(
        {
            "name": obj.name,
            "object_id": obj.object_id,
            "x": obj.tile.x,
            "y": obj.tile.y,
            "food_value": obj.food_value,
        }
        for obj in final.nearby_objects
        if obj.food_value > 0
    )

    checks = {
        "logged_in": client.logged_in,
        "self_player_known": client.self_player_id is not None,
        "world_state_ready": bool(final.facts.get("world_state_ready")),
        "tracked_objects_gt_0": int(final.facts.get("tracked_objects", 0)) > 0,
        "say_sent": any(item.get("type") == "say" for item in actions),
        "move_sent": any(item.get("type") == "move_to" for item in actions),
        "tile_changed": final.self.tile != initial.self.tile,
        "eat_attempted_if_food_visible": food is None or eat_attempted,
    }

    return LiveBehaviorReport(
        self_player_id=client.self_player_id,
        initial_tile=initial.self.tile,
        final_tile=final.self.tile,
        say_sent=checks["say_sent"],
        move_sent=checks["move_sent"],
        eat_attempted=eat_attempted,
        hunger_ratio=final.self.hunger_ratio,
        tracked_objects=int(final.facts.get("tracked_objects", 0)),
        nearby_food=nearby_food,
        checks=checks,
        actions=tuple(actions),
    )


def observation_summary(observation: Observation) -> dict[str, object]:
    return {
        "tick": observation.tick,
        "player_id": observation.self.player_id,
        "tile": {"x": observation.self.tile.x, "y": observation.self.tile.y},
        "age": observation.self.age,
        "food_store": observation.self.food_store,
        "max_food_store": observation.self.max_food_store,
        "hunger_ratio": observation.self.hunger_ratio,
        "tracked_objects": observation.facts.get("tracked_objects", 0),
        "nearby_food_count": sum(1 for obj in observation.nearby_objects if obj.food_value > 0),
        "nearby_object_count": len(observation.nearby_objects),
    }
