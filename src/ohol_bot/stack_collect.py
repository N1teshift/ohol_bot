from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .action_pending import PendingAction
from .harvest import merge_harvest_into_stack_rule
from .interact_flow import drop_candidates
from .model import Action, ActionType, ObjectState, Observation, PlayerState, Tile
from .movement_chat import optional_int
from .object_names import is_sharp_stone_name, normalize_item_name
from .spatial_queries import nearest_object, object_at_tile
from .tiles import danger_tiles, tile_set_from_facts

if TYPE_CHECKING:
    from .movement_policy import MovementFollowPolicy

@dataclass(slots=True)
class StackCollectState:
    requested_by: int
    item_name: str
    item_names: frozenset[str]
    pile_names: frozenset[str]
    depot_origin: Tile | None
    depot_tile: Tile | None
    loose_object_id: int | None = None
    pile_object_id: int | None = None
    depot_target_ids: tuple[int, ...] = ()
    source_target_ids: tuple[int, ...] = ()
    desired_count: int = 6
    deposited_count: int = 0
    drop_only: bool = False
    harvest_rule: dict[str, Any] | None = None
    deposit_pending: PendingAction = field(default_factory=PendingAction)


@dataclass(slots=True)
class CampSlotProgress:
    slot_id: int
    state: StackCollectState


@dataclass(slots=True)
class CampStockState:
    requested_by: int
    slots: tuple[CampSlotProgress, ...]


def resolve_stack_rule(observation: Observation, query: str) -> dict[str, Any]:
    normalized = normalize_item_name(query)
    catalog = observation.facts.get("stack_collect_catalog")
    harvest_catalog = observation.facts.get("harvest_catalog")
    if not isinstance(harvest_catalog, tuple):
        harvest_catalog = ()
    if isinstance(catalog, tuple):
        for raw_rule in catalog:
            if not isinstance(raw_rule, dict):
                continue
            aliases = raw_rule.get("query_aliases", ())
            loose_names = raw_rule.get("loose_names", ())
            pile_names = raw_rule.get("pile_names", ())
            if normalized in aliases or normalized in loose_names or normalized in pile_names:
                return merge_harvest_into_stack_rule(raw_rule, harvest_catalog)
    fallback = fallback_stack_rule(query)
    return merge_harvest_into_stack_rule(fallback, harvest_catalog)


def fallback_stack_rule(query: str) -> dict[str, Any]:
    normalized = normalize_item_name(query)
    display_name = query.strip().title()
    pile_name = f"{normalized} pile"
    return {
        "display_name": display_name,
        "loose_names": (normalized,),
        "pile_names": (pile_name,),
        "loose_object_id": None,
        "pile_object_id": None,
        "depot_target_ids": (),
        "source_target_ids": (),
        "query_aliases": (normalized, pile_name),
    }


def stack_state_from_rule(
    rule: dict[str, Any],
    *,
    requested_by: int,
    depot_origin: Tile | None,
    depot_tile: Tile | None,
    desired_count: int = 6,
) -> StackCollectState:
    loose_names = set(rule.get("loose_names", ()))
    harvest = rule.get("harvest")
    if isinstance(harvest, dict):
        loose_names.update(harvest.get("product_names", ()))
    return StackCollectState(
        requested_by=requested_by,
        item_name=str(rule.get("display_name", "item")),
        item_names=frozenset(loose_names),
        pile_names=frozenset(rule.get("pile_names", ())),
        depot_origin=depot_origin,
        depot_tile=depot_tile,
        loose_object_id=optional_int(rule.get("loose_object_id")),
        pile_object_id=optional_int(rule.get("pile_object_id")),
        depot_target_ids=tuple(rule.get("depot_target_ids", ())),
        source_target_ids=tuple(rule.get("source_target_ids", ())),
        desired_count=desired_count,
        drop_only=bool(rule.get("drop_only", False)),
        harvest_rule=harvest if isinstance(harvest, dict) else None,
    )


def camp_slot_needing_harvest(
    observation: Observation,
    camp: CampStockState,
) -> CampSlotProgress | None:
    candidates: list[CampSlotProgress] = []
    for slot in camp.slots:
        if slot.state.deposited_count >= slot.state.desired_count:
            continue
        if slot.state.harvest_rule is None:
            continue
        if holding_harvest_product(observation, slot.state.harvest_rule):
            continue
        if harvest_work_available(
            observation,
            slot.state.harvest_rule,
            slot.state.depot_tile,
        ):
            candidates.append(slot)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda slot: _harvest_work_distance(observation, slot.state),
    )


def harvest_work_available(
    observation: Observation,
    rule: dict[str, Any],
    depot_tile: Tile | None,
) -> bool:
    if _nearest_harvest_plant(observation, rule, depot_tile) is not None:
        return True
    return _nearest_harvest_dug(observation, rule, depot_tile) is not None


def _nearest_harvest_work_distance(
    observation: Observation,
    rule: dict[str, Any],
    depot_tile: Tile | None,
) -> int | None:
    plant = _nearest_harvest_plant(observation, rule, depot_tile)
    if plant is not None:
        return observation.self.tile.distance_to(plant.tile)
    dug = _nearest_harvest_dug(observation, rule, depot_tile)
    if dug is not None:
        return observation.self.tile.distance_to(dug.tile)
    return None


def _should_prefer_loose_over_harvest(
    observation: Observation,
    state: StackCollectState,
    policy: MovementFollowPolicy | None = None,
) -> bool:
    if state.harvest_rule is None:
        return False
    if not harvest_work_available(observation, state.harvest_rule, state.depot_tile):
        return False
    loose = nearest_stack_source(observation, state, policy)
    if loose is None or not is_stack_loose_source(loose, state):
        return False
    harvest_distance = _nearest_harvest_work_distance(
        observation,
        state.harvest_rule,
        state.depot_tile,
    )
    if harvest_distance is None:
        return True
    return observation.self.tile.distance_to(loose.tile) <= harvest_distance


def _is_holding_surplus_camp_item(
    observation: Observation,
    camp: CampStockState,
) -> bool:
    if camp_slot_for_held_item(observation, camp) is not None:
        return False
    for slot in camp.slots:
        if is_holding_collect_target(observation, slot.state.item_names):
            return True
        rule = slot.state.harvest_rule
        if rule is not None and holding_harvest_product(observation, rule):
            return True
    return False


def _harvest_work_distance(observation: Observation, state: StackCollectState) -> int:
    rule = state.harvest_rule
    if rule is None:
        return 10_000
    plant = _nearest_harvest_plant(observation, rule, state.depot_tile)
    if plant is not None:
        return observation.self.tile.distance_to(plant.tile)
    dug = _nearest_harvest_dug(observation, rule, state.depot_tile)
    if dug is not None:
        return observation.self.tile.distance_to(dug.tile)
    tool = _nearest_loose_harvest_tool(observation, rule)
    if tool is not None:
        return observation.self.tile.distance_to(tool.tile)
    stone = _nearest_loose_stone(observation)
    if stone is not None:
        return observation.self.tile.distance_to(stone.tile)
    return 10_000


def holding_harvest_product(observation: Observation, rule: dict[str, Any]) -> bool:
    product_ids = rule.get("product_object_ids") or rule.get("product_object_id")
    if isinstance(product_ids, int):
        product_ids = (product_ids,)
    if isinstance(product_ids, tuple) and observation.self.held_object_id in product_ids:
        return True
    held_name = observation.self.held_object_name
    if held_name is None:
        return False
    normalized = normalize_item_name(held_name)
    return normalized in rule.get("product_names", ())


def _holding_harvest_tool(observation: Observation, rule: dict[str, Any]) -> bool:
    tool_ids = rule.get("tool_object_ids", ())
    if observation.self.held_object_id in tool_ids:
        return True
    held_name = observation.self.held_object_name
    if held_name is None:
        return False
    normalized = normalize_item_name(held_name)
    return normalized in rule.get("tool_names", ())


def object_matches_harvest_dug(obj: ObjectState, rule: dict[str, Any]) -> bool:
    dug_id = rule.get("dug_object_id")
    if isinstance(dug_id, int) and obj.object_id == dug_id:
        return True
    return normalize_item_name(obj.name) in rule.get("dug_names", ())


def object_matches_harvest_plant(obj: ObjectState, rule: dict[str, Any]) -> bool:
    plant_ids = set(rule.get("plant_object_ids", ()))
    return obj.object_id in plant_ids


def _harvest_work_tile_valid(
    observation: Observation,
    work_tile: Tile,
    rule: dict[str, Any],
) -> bool:
    obj = object_at_tile(observation, work_tile)
    if obj is None:
        return False
    return object_matches_harvest_plant(obj, rule) or object_matches_harvest_dug(
        obj, rule
    )


def _nearest_harvest_plant(
    observation: Observation,
    rule: dict[str, Any],
    depot_tile: Tile | None,
) -> ObjectState | None:
    return nearest_object(
        observation,
        predicate=lambda obj: object_matches_harvest_plant(obj, rule),
        skip_depot=depot_tile,
    )


def _nearest_harvest_dug(
    observation: Observation,
    rule: dict[str, Any],
    depot_tile: Tile | None,
) -> ObjectState | None:
    dug_id = rule.get("dug_object_id")
    if not isinstance(dug_id, int):
        return None
    return nearest_object(
        observation,
        object_ids=frozenset({dug_id}),
        skip_depot=depot_tile,
    )


def _nearest_loose_harvest_tool(
    observation: Observation,
    rule: dict[str, Any],
) -> ObjectState | None:
    tool_ids = set(rule.get("tool_object_ids", ()))
    tool_names = set(rule.get("tool_names", ()))
    return nearest_object(
        observation,
        predicate=lambda obj: (
            obj.object_id in tool_ids or normalize_item_name(obj.name) in tool_names
        ),
        skip_danger=False,
    )


def _nearest_loose_sharp_stone(observation: Observation) -> ObjectState | None:
    return nearest_object(
        observation,
        predicate=lambda obj: is_sharp_stone_name(obj.name),
        skip_danger=False,
    )


def camp_stock_state_from_layout(
    observation: Observation,
    layout: Any,
    *,
    requested_by: int,
) -> CampStockState:
    slots: list[CampSlotProgress] = []
    for slot_spec in layout.slots:
        rule = resolve_stack_rule(observation, slot_spec.item_query)
        stack_state = stack_state_from_rule(
            rule,
            requested_by=requested_by,
            depot_origin=None,
            depot_tile=slot_spec.tile,
            desired_count=slot_spec.desired_count,
        )
        slots.append(CampSlotProgress(slot_id=slot_spec.slot_id, state=stack_state))
    return CampStockState(requested_by=requested_by, slots=tuple(slots))


def camp_stock_complete(camp: CampStockState) -> bool:
    return all(
        slot.state.deposited_count >= slot.state.desired_count for slot in camp.slots
    )


def camp_stock_deposit_settle_reason(
    policy: MovementFollowPolicy,
    observation: Observation,
    camp: CampStockState,
) -> str | None:
    for slot in camp.slots:
        reason = policy._collect_stack_deposit_settle_reason(observation, slot.state)
        if reason is not None:
            return reason.replace("stack", "stock camp")
    return None


def camp_slot_for_held_item(
    observation: Observation,
    camp: CampStockState,
) -> CampSlotProgress | None:
    matching: list[CampSlotProgress] = []
    for slot in camp.slots:
        if slot.state.deposited_count >= slot.state.desired_count:
            continue
        if slot.state.depot_tile is None:
            continue
        if is_holding_collect_target(observation, slot.state.item_names):
            matching.append(slot)
    if not matching:
        return None
    return min(
        matching,
        key=lambda slot: observation.self.tile.distance_to(slot.state.depot_tile),
    )


def select_camp_work(
    observation: Observation,
    camp: CampStockState,
    policy: MovementFollowPolicy,
) -> tuple[ObjectState, CampSlotProgress] | None:
    best: tuple[int, ObjectState, CampSlotProgress] | None = None
    for slot in camp.slots:
        if slot.state.deposited_count >= slot.state.desired_count:
            continue
        source = nearest_stack_source(observation, slot.state)
        if source is None:
            continue
        distance = observation.self.tile.distance_to(source.tile)
        if best is None or distance < best[0]:
            best = (distance, source, slot)
    if best is None:
        return None
    policy._stack_source_tile = best[1].tile
    policy._stack_source_set_tick = observation.tick
    return best[1], best[2]


def decide_stack_deposit_action(
    observation: Observation,
    state: StackCollectState,
    depot: Tile,
    depot_object: ObjectState | None,
    policy: MovementFollowPolicy,
    *,
    slot_id: int | None = None,
) -> tuple[Action, str] | None:
    drop_only = state.drop_only
    slot_prefix = f"camp slot {slot_id} " if slot_id is not None else ""
    progress = f"{state.deposited_count + 1}/{state.desired_count}"

    if depot_object is None:
        policy._note_stack_deposit_attempt(observation, state, depot)
        reason = f"{slot_prefix}start {state.item_name} stack {progress}"
        return (
            Action(ActionType.DROP, {"x": depot.x, "y": depot.y}),
            reason,
        )

    if not is_stack_depot_object(depot_object, state):
        return None

    policy._note_stack_deposit_attempt(observation, state, depot)
    if drop_only:
        reason = f"{slot_prefix}add {state.item_name} {progress}"
        return (
            Action(ActionType.DROP, {"x": depot.x, "y": depot.y}),
            reason,
        )

    reason = f"{slot_prefix}add {state.item_name} to stack {progress}"
    return (
        Action(
            ActionType.USE,
            {
                "target_x": depot.x,
                "target_y": depot.y,
                "expect_empty_hands": True,
            },
        ),
        reason,
    )


def player_by_id(observation: Observation, player_id: int) -> PlayerState | None:
    for player in observation.nearby_players:
        if player.player_id == player_id:
            return player
    return None


def speaker_tile(observation: Observation, player_id: int) -> Tile | None:
    speaker = player_by_id(observation, player_id)
    if speaker is not None:
        return speaker.tile
    for event in reversed(_chat_events(observation)):
        if event.get("player_id") != player_id:
            continue
        raw = event.get("speaker_tile")
        if isinstance(raw, dict) and "x" in raw and "y" in raw:
            return Tile(int(raw["x"]), int(raw["y"]))
        break
    return None


def nearest_named_object(
    observation: Observation,
    names: frozenset[str],
) -> ObjectState | None:
    if not names:
        return None
    return nearest_object(observation, names=names)


def is_stack_loose_source(
    obj: ObjectState,
    state: StackCollectState,
) -> bool:
    rule = state.harvest_rule
    if rule is not None:
        if object_matches_harvest_plant(obj, rule):
            return False
        dug_id = rule.get("dug_object_id")
        if isinstance(dug_id, int) and obj.object_id == dug_id:
            return False
        product_id = rule.get("product_object_id")
        if isinstance(product_id, int) and obj.object_id == product_id:
            return True
        return False
    if state.loose_object_id is not None and obj.object_id == state.loose_object_id:
        return True
    return normalize_item_name(obj.name) in state.item_names


def nearest_stack_source(
    observation: Observation,
    state: StackCollectState,
    policy: MovementFollowPolicy | None = None,
) -> ObjectState | None:
    danger = danger_tiles(observation)
    candidates: list[ObjectState] = []
    for obj in observation.nearby_objects:
        if obj.tile == state.depot_tile:
            continue
        if obj.tile in danger:
            continue
        if policy is not None and policy._camp_pickup_ignored(observation, obj.tile):
            continue
        if is_stack_loose_source(obj, state):
            candidates.append(obj)
        elif is_stack_pile_source(obj, state):
            candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: observation.self.tile.distance_to(obj.tile))


def select_stack_source(
    observation: Observation,
    state: StackCollectState,
    policy: MovementFollowPolicy,
) -> ObjectState | None:
    danger = danger_tiles(observation)
    now_tick = observation.tick
    if (
        policy._stack_source_tile is not None
        and now_tick - policy._stack_source_set_tick
        < policy.config.stack_source_retarget_cooldown_ticks
    ):
        for obj in observation.nearby_objects:
            if obj.tile == policy._stack_source_tile and obj.tile not in danger:
                if obj.tile == state.depot_tile:
                    continue
                if policy._camp_pickup_ignored(observation, obj.tile):
                    continue
                if is_stack_loose_source(obj, state) or is_stack_pile_source(
                    obj, state
                ):
                    return obj

    selected = nearest_stack_source(observation, state)
    if selected is not None:
        policy._stack_source_tile = selected.tile
        policy._stack_source_set_tick = now_tick
    else:
        policy._stack_source_tile = None
    return selected


def is_stack_pile_source(
    obj: ObjectState,
    state: StackCollectState,
) -> bool:
    if state.pile_object_id is not None and obj.object_id == state.pile_object_id:
        return True
    if obj.object_id in state.source_target_ids:
        return True
    name = normalize_item_name(obj.name)
    if name in state.pile_names or name_is_item_pile(name, state):
        return True
    return False


def is_holding_collect_target(
    observation: Observation,
    names: frozenset[str],
) -> bool:
    held_name = observation.self.held_object_name
    if held_name is None:
        return False
    return normalize_item_name(held_name) in names


def select_stack_depot_tile(
    observation: Observation,
    origin: Tile,
    state: StackCollectState,
) -> Tile | None:
    blocked = tile_set_from_facts(observation.facts.get("blocked_tiles"))
    blocked.update(tile_set_from_facts(observation.facts.get("known_blocking_tiles")))
    blocked.update(tile_set_from_facts(observation.facts.get("avoid_targets")))
    blocked.update(tile_set_from_facts(observation.facts.get("danger_tiles")))
    occupied_by_players = {player.tile for player in observation.nearby_players}
    candidates = drop_candidates(origin)
    for tile in candidates:
        if tile in blocked or tile in occupied_by_players:
            continue
        obj = object_at_tile(observation, tile)
        if obj is None or is_stack_depot_object(obj, state):
            return tile
    return None


def is_stack_depot_object(
    obj: ObjectState,
    state: StackCollectState,
) -> bool:
    if state.loose_object_id is not None and obj.object_id == state.loose_object_id:
        return True
    if state.pile_object_id is not None and obj.object_id == state.pile_object_id:
        return True
    if obj.object_id in state.depot_target_ids:
        return True
    name = normalize_item_name(obj.name)
    if name in state.item_names or name in state.pile_names:
        return True
    if name_is_item_pile(name, state):
        return True
    # Server-generated stack states may use ids missing from local game_data.
    if name.startswith("unknown:"):
        return True
    return False


def name_is_item_pile(name: str, state: StackCollectState) -> bool:
    for base in state.item_names:
        if name == f"{base} pile":
            return True
        if base in name and "pile" in name:
            return True
    return False


# Public aliases for harvest helpers used by movement_policy
holding_harvest_tool = _holding_harvest_tool
harvest_work_tile_valid = _harvest_work_tile_valid
nearest_harvest_plant = _nearest_harvest_plant
nearest_harvest_dug = _nearest_harvest_dug
nearest_loose_harvest_tool = _nearest_loose_harvest_tool
nearest_loose_sharp_stone = _nearest_loose_sharp_stone
_should_prefer_loose_over_harvest = _should_prefer_loose_over_harvest
is_holding_surplus_camp_item = _is_holding_surplus_camp_item

# Test/backward-compat re-exports
_nearest_harvest_plant = _nearest_harvest_plant
_nearest_stack_source = nearest_stack_source
_camp_stock_state_from_layout = camp_stock_state_from_layout
