from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .biomes import BiomeCatalog, load_biome_catalog


@dataclass(frozen=True, slots=True)
class OholObject:
    object_id: int
    name: str
    blocks_walking: bool = False
    left_blocking_radius: int = 0
    right_blocking_radius: int = 0
    food_value: int = 0
    num_uses: int = 1
    deadly_distance: int = 0
    spawn_biomes: frozenset[int] = frozenset()
    male: bool = True
    race: int = 0
    home_marker: bool = False


RACE_NAMES: dict[int, str] = {
    1: "African",
    2: "Asian",
    3: "Caucasian",
    4: "Native",
}


def race_name_for_id(race_id: int) -> str | None:
    return RACE_NAMES.get(race_id)


@dataclass(frozen=True, slots=True)
class OholTransition:
    actor_id: int
    target_id: int
    new_actor_id: int
    new_target_id: int


@dataclass(frozen=True, slots=True)
class OholGameData:
    objects: dict[int, OholObject]
    transitions: tuple[OholTransition, ...]
    biomes: BiomeCatalog

    def object_name(self, object_id: int) -> str:
        obj = self.objects.get(object_id)
        return obj.name if obj else f"unknown:{object_id}"

    def biome_name(self, biome_id: int) -> str:
        return self.biomes.biome_name(biome_id)


def load_game_data(root: str | Path, *, include_transitions: bool = True) -> OholGameData:
    root_path = Path(root)
    return OholGameData(
        objects=load_objects(root_path / "objects"),
        transitions=(
            load_transitions(root_path / "transitions")
            if include_transitions
            else tuple()
        ),
        biomes=load_biome_catalog(root_path),
    )


def load_objects(objects_path: str | Path) -> dict[int, OholObject]:
    path = Path(objects_path)
    objects: dict[int, OholObject] = {}
    for object_file in path.glob("*.txt"):
        if not object_file.stem.isdigit():
            continue
        obj = parse_object_file(object_file)
        objects[obj.object_id] = obj
    return objects


def parse_object_file(path: str | Path) -> OholObject:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    object_id = _parse_int_value(lines[0], "id", int(Path(path).stem))
    name = lines[1].strip() if len(lines) > 1 else f"unknown:{object_id}"
    values = _key_values(lines)
    return OholObject(
        object_id=object_id,
        name=name,
        blocks_walking=values.get("blocksWalking", "0") == "1",
        left_blocking_radius=_safe_int(values.get("leftBlockingRadius", "0"), 0),
        right_blocking_radius=_safe_int(values.get("rightBlockingRadius", "0"), 0),
        food_value=_safe_int(values.get("foodValue", "0"), 0),
        num_uses=_safe_int(values.get("numUses", "1").split(",", maxsplit=1)[0], 1),
        deadly_distance=_safe_int(values.get("deadlyDistance", "0"), 0),
        spawn_biomes=_parse_spawn_biomes(lines),
        male=values.get("male", "1") != "0",
        race=_safe_int(values.get("race", "0"), 0) or 0,
        home_marker=values.get("homeMarker", "0") == "1",
    )


def load_transitions(transitions_path: str | Path) -> tuple[OholTransition, ...]:
    path = Path(transitions_path)
    transitions: list[OholTransition] = []
    if not path.exists():
        return tuple()
    for transition_file in path.glob("*.txt"):
        parsed = parse_transition_file(transition_file)
        if parsed is not None:
            transitions.append(parsed)
    return tuple(transitions)


def parse_transition_file(path: str | Path) -> OholTransition | None:
    path = Path(path)
    if "_" not in path.stem:
        return None
    actor_raw, target_raw = path.stem.split("_", maxsplit=1)
    target_raw = target_raw.split("_", maxsplit=1)[0]
    if not _maybe_signed_int(actor_raw) or not _maybe_signed_int(target_raw):
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    first_fields = lines[0].split() if lines else []
    values = _key_values(lines)
    return OholTransition(
        actor_id=int(actor_raw),
        target_id=int(target_raw),
        new_actor_id=_safe_int(
            values.get("newActor", first_fields[0] if len(first_fields) > 0 else "0"),
            0,
        ),
        new_target_id=_safe_int(
            values.get("newTarget", first_fields[1] if len(first_fields) > 1 else "0"),
            0,
        ),
    )


def _key_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        for hash_part in line.split("#"):
            for part in hash_part.split(","):
                if "=" not in part:
                    continue
                key, value = part.split("=", maxsplit=1)
                values[key.strip()] = value.strip()
    return values


def _parse_int_value(line: str, key: str, default: int) -> int:
    prefix = f"{key}="
    if line.startswith(prefix):
        return _safe_int(line[len(prefix) :], default)
    return default


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _maybe_signed_int(value: str) -> bool:
    return value.lstrip("-").isdigit()


def _parse_spawn_biomes(lines: list[str]) -> frozenset[int]:
    biome_ids: set[int] = set()
    for line in lines:
        match = re.search(r"biomes_([\d,]+)", line)
        if match is None:
            continue
        for token in match.group(1).split(","):
            token = token.strip()
            if token.isdigit():
                biome_ids.add(int(token))
    return frozenset(biome_ids)


def _normalize_object_name(name: str) -> str:
    return name.strip().lower()


def build_stack_collect_catalog(
    game_data: OholGameData | None,
) -> tuple[dict[str, Any], ...]:
    """Map stackable loose items to pile objects and transition target ids."""
    if game_data is None:
        return ()

    loose_by_name = {
        _normalize_object_name(obj.name): obj for obj in game_data.objects.values()
    }
    rules: list[dict[str, Any]] = []
    seen_loose_ids: set[int] = set()

    for pile_obj in game_data.objects.values():
        pile_name = _normalize_object_name(pile_obj.name)
        if not pile_name.endswith(" pile"):
            continue
        loose_name = pile_name[: -len(" pile")].strip()
        loose_obj = loose_by_name.get(loose_name)
        if loose_obj is None or loose_obj.object_id in seen_loose_ids:
            continue

        loose_id = loose_obj.object_id
        pile_id = pile_obj.object_id
        seen_loose_ids.add(loose_id)
        loose_names = (loose_name,)
        pile_names = (pile_name,)
        depot_target_ids = tuple(
            sorted(
                {
                    transition.target_id
                    for transition in game_data.transitions
                    if transition.actor_id == loose_id
                    and transition.new_target_id == pile_id
                }
            )
        )
        source_target_ids = tuple(
            sorted(
                {
                    transition.target_id
                    for transition in game_data.transitions
                    if transition.actor_id == 0 and transition.new_actor_id == loose_id
                }
            )
        )
        aliases = tuple(sorted({loose_name, pile_name, loose_name.replace(" ", "")}))
        rules.append(
            {
                "display_name": loose_obj.name,
                "loose_names": loose_names,
                "pile_names": pile_names,
                "loose_object_id": loose_id,
                "pile_object_id": pile_id,
                "depot_target_ids": depot_target_ids,
                "source_target_ids": source_target_ids,
                "query_aliases": aliases,
            }
        )

    return tuple(rules)


# Manual camp-depot stack rules for piles that auto-catalog misses (non "{name} pile" names).
_CAMP_STACK_SPECS: tuple[dict[str, Any], ...] = (
    {
        "loose_name": "stone",
        "pile_names": ("stone pile",),
        "aliases": ("stones",),
    },
    {
        "loose_name": "sharp stone",
        "pile_names": ("pile of sharp stones",),
        "aliases": ("sharp stones",),
    },
    {
        "loose_name": "flint",
        "pile_names": (),
        "aliases": ("flints",),
        "drop_only": True,
    },
    {
        "loose_name": "wild onion",
        "pile_names": ("pile of wild onions",),
        "aliases": ("wild onions", "onion", "onions"),
    },
    {
        "loose_name": "wild carrot",
        "pile_names": ("pile of wild carrots", "carrot pile"),
        "aliases": ("wild carrots", "carrot", "carrots"),
    },
    {
        "loose_name": "burdock",
        "pile_names": ("pile of burdock roots",),
        "aliases": ("burdocks", "burdock root", "burdock roots"),
    },
    {
        "loose_name": "wild garlic",
        "pile_names": ("pile of wild garlic", "garlic bulb pile"),
        "aliases": ("wild garlics", "garlic", "garlics"),
    },
    {
        "loose_name": "straight branch",
        "pile_names": ("pile of straight branches",),
        "aliases": (
            "straight branches",
            "long branch",
            "long branches",
            "branch",
            "branches",
        ),
    },
)


def _object_by_normalized_name(
    game_data: OholGameData,
    name: str,
) -> OholObject | None:
    normalized = _normalize_object_name(name)
    for obj in game_data.objects.values():
        if _normalize_object_name(obj.name) == normalized:
            return obj
    return None


def _transition_ids_for_stack(
    game_data: OholGameData,
    *,
    loose_id: int,
    pile_id: int | None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if pile_id is None:
        return (), ()
    depot_target_ids = tuple(
        sorted(
            {
                transition.target_id
                for transition in game_data.transitions
                if transition.actor_id == loose_id
                and transition.new_target_id == pile_id
            }
        )
    )
    source_target_ids = tuple(
        sorted(
            {
                transition.target_id
                for transition in game_data.transitions
                if transition.actor_id == 0 and transition.new_actor_id == loose_id
            }
        )
    )
    return depot_target_ids, source_target_ids


def build_camp_stack_rules(
    game_data: OholGameData | None,
) -> tuple[dict[str, Any], ...]:
    if game_data is None:
        return ()

    rules: list[dict[str, Any]] = []
    for spec in _CAMP_STACK_SPECS:
        loose_name = spec["loose_name"]
        loose_obj = _object_by_normalized_name(game_data, loose_name)
        if loose_obj is None:
            continue
        pile_names: tuple[str, ...] = spec.get("pile_names", ())
        pile_obj = None
        for pile_name in pile_names:
            pile_obj = _object_by_normalized_name(game_data, pile_name)
            if pile_obj is not None:
                break
        loose_id = loose_obj.object_id
        pile_id = pile_obj.object_id if pile_obj is not None else None
        depot_target_ids, source_target_ids = _transition_ids_for_stack(
            game_data,
            loose_id=loose_id,
            pile_id=pile_id,
        )
        aliases = tuple(
            sorted(
                {
                    loose_name,
                    *pile_names,
                    *spec.get("aliases", ()),
                    loose_name.replace(" ", ""),
                }
            )
        )
        rules.append(
            {
                "display_name": loose_obj.name,
                "loose_names": (loose_name,),
                "pile_names": pile_names,
                "loose_object_id": loose_id,
                "pile_object_id": pile_id,
                "depot_target_ids": depot_target_ids,
                "source_target_ids": source_target_ids,
                "query_aliases": aliases,
                "drop_only": bool(spec.get("drop_only", False)),
            }
        )
    return tuple(rules)


def merge_camp_stack_catalog(
    catalog: tuple[dict[str, Any], ...],
    game_data: OholGameData | None,
) -> tuple[dict[str, Any], ...]:
    """Merge auto-catalog rules with camp overrides (camp wins on loose_object_id)."""
    camp_rules = build_camp_stack_rules(game_data)
    if not camp_rules:
        return catalog
    by_loose_id: dict[int, dict[str, Any]] = {}
    for rule in catalog:
        loose_id = rule.get("loose_object_id")
        if isinstance(loose_id, int):
            by_loose_id[loose_id] = dict(rule)
    for rule in camp_rules:
        loose_id = rule.get("loose_object_id")
        if isinstance(loose_id, int):
            by_loose_id[loose_id] = dict(rule)
    return tuple(by_loose_id[loose_id] for loose_id in sorted(by_loose_id))
