from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .model import Observation, PlayerState, Tile

if TYPE_CHECKING:
    from .movement_policy import MovementFollowPolicy


def annotate_movement_facts(
    policy: MovementFollowPolicy,
    observation: Observation,
    *,
    leader: PlayerState | None = None,
    leader_distance: int | None = None,
    target: Tile | None = None,
    reason: str,
    collect_reason: str | None = None,
    collect_target: Tile | None = None,
    collect_target_name: str | None = None,
) -> None:
    observation.facts["movement_mode"] = policy.mode
    observation.facts["follow_leader_id"] = policy.leader_id
    observation.facts["follow_reason"] = reason
    observation.facts["follow_target"] = (
        {"x": target.x, "y": target.y} if target is not None else None
    )
    observation.facts["follow_leader_tile"] = (
        {"x": leader.tile.x, "y": leader.tile.y} if leader is not None else None
    )
    observation.facts["follow_leader_distance"] = leader_distance
    observation.facts["follow_last_chat_sequence"] = policy._last_chat_sequence
    observation.facts["collect_requested_by"] = policy.collect_requested_by
    observation.facts["collect_names"] = tuple(sorted(policy.collect_names))
    observation.facts["collect_target_name"] = collect_target_name
    observation.facts["collect_target"] = (
        {"x": collect_target.x, "y": collect_target.y}
        if collect_target is not None
        else None
    )
    observation.facts["collect_reason"] = collect_reason
    observation.facts["make_sharp_stone_requested_by"] = policy.make_sharp_stone_requested_by
    observation.facts["stock_camp_requested_by"] = policy.stock_camp_requested_by
    camp = policy.camp_stock
    observation.facts["camp_stock"] = (
        {
            "requested_by": camp.requested_by,
            "slots": tuple(
                {
                    "slot_id": slot.slot_id,
                    "item_name": slot.state.item_name,
                    "desired_count": slot.state.desired_count,
                    "deposited_count": slot.state.deposited_count,
                    "depot_tile": (
                        {"x": slot.state.depot_tile.x, "y": slot.state.depot_tile.y}
                        if slot.state.depot_tile is not None
                        else None
                    ),
                }
                for slot in camp.slots
            ),
        }
        if camp is not None
        else None
    )
    stack = policy.collect_stack
    observation.facts["collect_stack"] = (
        {
            "requested_by": stack.requested_by,
            "item_name": stack.item_name,
            "desired_count": stack.desired_count,
            "deposited_count": stack.deposited_count,
            "depot_origin": (
                {"x": stack.depot_origin.x, "y": stack.depot_origin.y}
                if stack.depot_origin is not None
                else None
            ),
            "depot_tile": (
                {"x": stack.depot_tile.x, "y": stack.depot_tile.y}
                if stack.depot_tile is not None
                else None
            ),
            "pending_deposit_tile": (
                {
                    "x": stack.deposit_pending.tile.x,
                    "y": stack.deposit_pending.tile.y,
                }
                if stack.deposit_pending.tile is not None
                else None
            ),
        }
        if stack is not None
        else None
    )


@dataclass(frozen=True, slots=True)
class MovementFacts:
    movement_mode: str | None = None
    follow_leader_id: int | None = None
    follow_reason: str | None = None
    collect_reason: str | None = None

    @classmethod
    def from_observation(cls, observation: Observation) -> MovementFacts:
        facts: dict[str, Any] = observation.facts
        return cls(
            movement_mode=facts.get("movement_mode"),
            follow_leader_id=facts.get("follow_leader_id"),
            follow_reason=facts.get("follow_reason"),
            collect_reason=facts.get("collect_reason"),
        )
