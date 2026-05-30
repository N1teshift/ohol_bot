from __future__ import annotations

from .model import Observation, PlayerState

# OneLife client uses noMoveAge = 0.20 — younger babies cannot move or self-act.
NO_MOVE_AGE = 0.20

# Planner treats the bot as hungry when this many base stomach pips are empty.
HUNGER_MISSING_PIPS_THRESHOLD = 1

# Stop waiting for an eat response after this many world-state ticks.
EAT_PENDING_TIMEOUT_TICKS = 8


def is_planner_hungry(player: PlayerState) -> bool:
    return player.missing_food_pips >= HUNGER_MISSING_PIPS_THRESHOLD


def can_self_act(player: PlayerState) -> bool:
    return player.age >= NO_MOVE_AGE


def hunger_rule_text() -> str:
    threshold = HUNGER_MISSING_PIPS_THRESHOLD
    pip_word = "pip" if threshold == 1 else "pips"
    return f">={threshold} missing base {pip_word}"


def eat_blocker(observation: Observation) -> str | None:
    player = observation.self
    if observation.facts.get("eat_pending"):
        return "waiting for server eat response"
    if not can_self_act(player):
        return f"too young to self-act (age {player.age:.2f} < {NO_MOVE_AGE})"
    if not player.is_stationary:
        return "still moving — must stand still to eat"
    return None


def action_blocker(observation: Observation) -> str | None:
    player = observation.self
    if player.is_being_carried:
        return "being carried"
    if not player.is_stationary:
        return "still moving — finish current step first"
    return None


def forage_blocker(observation: Observation) -> str | None:
    player = observation.self
    if player.is_being_carried:
        return "being carried"
    if not is_planner_hungry(player):
        return None
    if player.is_holding_food:
        return eat_blocker(observation)
    if observation.nearest_food() is not None:
        return None
    return "no edible objects within range"