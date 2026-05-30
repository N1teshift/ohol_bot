from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .biomes import BiomeCatalog, load_biome_catalog


@dataclass(frozen=True, slots=True)
class OholObject:
    object_id: int
    name: str
    blocks_walking: bool = False
    food_value: int = 0
    num_uses: int = 1
    spawn_biomes: frozenset[int] = frozenset()


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


def load_game_data(root: str | Path) -> OholGameData:
    root_path = Path(root)
    return OholGameData(
        objects=load_objects(root_path / "objects"),
        transitions=load_transitions(root_path / "transitions"),
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
        food_value=_safe_int(values.get("foodValue", "0"), 0),
        num_uses=_safe_int(values.get("numUses", "1").split(",", maxsplit=1)[0], 1),
        spawn_biomes=_parse_spawn_biomes(lines),
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
        for part in line.split("#"):
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
