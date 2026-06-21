from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .collect_rules import HarvestRule
    from .game_data import OholGameData


from .object_names import normalize_item_name as _normalize_object_name

# Dig-harvest plants for camp stocking. Tool order: sharp stone first, then sandbox digger.
_MANUAL_HARVEST_SPECS: tuple[dict[str, Any], ...] = (
    {
        "query": "wild carrot",
        "plant_ids": (404, 36),
        "product_id": 40,
        "dug_id": 39,
        "tool_ids": (34, 722),
    },
    {
        "query": "burdock",
        "plant_ids": (804,),
        "product_id": 807,
        "dug_id": 806,
        "tool_ids": (34, 722),
    },
    {
        "query": "flint",
        "plant_ids": (133,),
        "product_id": 135,
        "dug_id": 150,
        "tool_ids": (34,),
    },
)


def build_harvest_catalog(
    game_data: OholGameData | None,
) -> tuple[dict[str, Any], ...]:
    return tuple(rule.to_dict() for rule in build_harvest_rules(game_data))


def build_harvest_rules(
    game_data: OholGameData | None,
) -> tuple[HarvestRule, ...]:
    from .collect_rules import HarvestRule

    if game_data is None:
        return ()

    names = {obj.object_id: obj.name for obj in game_data.objects.values()}
    rules: list[HarvestRule] = []

    for spec in _MANUAL_HARVEST_SPECS:
        plant_ids = tuple(
            pid for pid in spec["plant_ids"] if pid in names
        )
        product_id = spec["product_id"]
        dug_id = spec["dug_id"]
        if product_id not in names or dug_id not in names or not plant_ids:
            continue

        tool_ids: list[int] = []
        for tool_id in spec["tool_ids"]:
            if tool_id in names:
                discovered = _discover_tool_for_plant(game_data, plant_ids[0], tool_id)
                if discovered is not None or tool_id in spec["tool_ids"][:1]:
                    if tool_id not in tool_ids:
                        tool_ids.append(tool_id)

        if not tool_ids:
            discovered = _discover_tool_for_plant(game_data, plant_ids[0], None)
            if discovered is not None and discovered not in tool_ids:
                tool_ids.append(discovered)

        product_name = _normalize_object_name(names[product_id])
        plant_names = tuple(
            sorted({_normalize_object_name(names[pid]) for pid in plant_ids})
        )
        dug_name = _normalize_object_name(names[dug_id])
        tool_names = tuple(
            sorted({_normalize_object_name(names[tid]) for tid in tool_ids if tid in names})
        )
        aliases = tuple(
            sorted(
                {
                    spec["query"],
                    product_name,
                    *plant_names,
                    dug_name,
                    *tool_names,
                    spec["query"].replace(" ", ""),
                }
            )
        )
        rules.append(
            HarvestRule(
                query=spec["query"],
                display_name=names[product_id],
                plant_object_ids=plant_ids,
                plant_names=plant_names,
                dug_object_id=dug_id,
                dug_names=(dug_name,),
                product_object_id=product_id,
                product_names=(product_name,),
                tool_object_ids=tuple(tool_ids),
                tool_names=tool_names,
                query_aliases=aliases,
            )
        )

    return tuple(rules)


def merge_harvest_into_stack_rule(
    rule: dict[str, Any],
    harvest_catalog: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    merged = dict(rule)
    normalized_aliases = set(rule.get("query_aliases", ()))
    normalized_aliases.add(_normalize_object_name(str(rule.get("display_name", ""))))
    for loose in rule.get("loose_names", ()):
        normalized_aliases.add(_normalize_object_name(str(loose)))

    for harvest in harvest_catalog:
        harvest_aliases = set(harvest.get("query_aliases", ()))
        if not normalized_aliases.intersection(harvest_aliases):
            continue
        merged["harvest"] = dict(harvest)
        merged["display_name"] = harvest["display_name"]
        merged["loose_object_id"] = harvest["product_object_id"]
        loose_names = set(rule.get("loose_names", ()))
        loose_names.update(harvest.get("product_names", ()))
        merged["loose_names"] = tuple(sorted(loose_names))
        merged["item_names"] = tuple(harvest.get("product_names", ()))
        aliases = set(rule.get("query_aliases", ()))
        aliases.update(harvest.get("query_aliases", ()))
        merged["query_aliases"] = tuple(sorted(aliases))
        break
    return merged


def harvest_rule_for_query(
    harvest_catalog: tuple[dict[str, Any], ...],
    query: str,
) -> dict[str, Any] | None:
    normalized = _normalize_object_name(query)
    for rule in harvest_catalog:
        if normalized in rule.get("query_aliases", ()):
            return rule
        if normalized == _normalize_object_name(rule.get("query", "")):
            return rule
    return None


def _discover_tool_for_plant(
    game_data: OholGameData,
    plant_id: int,
    preferred_tool_id: int | None,
) -> int | None:
    for transition in game_data.transitions:
        if transition.target_id != plant_id:
            continue
        if transition.actor_id == 0:
            continue
        if preferred_tool_id is not None and transition.actor_id != preferred_tool_id:
            continue
        return transition.actor_id
    return None
