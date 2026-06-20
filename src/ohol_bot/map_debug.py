from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .model import Observation, Tile


@dataclass(frozen=True, slots=True)
class MapRenderConfig:
    radius: int = 10
    max_object_labels: int = 8


def render_observation_map(
    observation: Observation,
    *,
    config: MapRenderConfig | None = None,
) -> str:
    """Render a compact tile map around the bot using observation facts."""
    cfg = config or MapRenderConfig()
    radius = max(1, cfg.radius)
    center = observation.self.tile
    objects = {obj.tile: obj for obj in observation.nearby_objects}
    players = {player.tile: player for player in observation.nearby_players}
    blocked = _tile_set(observation.facts.get("known_blocking_tiles"))
    blocked.update(_tile_set(observation.facts.get("blocked_tiles")))
    avoided = _tile_set(observation.facts.get("avoid_targets"))
    path = _tile_sequence(observation.facts.get("last_move_path"))
    path_tiles = set(path)
    follow_target = _fact_tile(observation.facts.get("follow_target"))
    leader_tile = _fact_tile(observation.facts.get("follow_leader_tile"))
    collect_target = _fact_tile(observation.facts.get("collect_target"))
    camp_slots = _camp_slot_tiles(observation.facts.get("camp_layout"))
    camp_fire = _fact_tile(
        observation.facts.get("camp_layout", {}).get("fire_tile")
        if isinstance(observation.facts.get("camp_layout"), dict)
        else None
    )

    lines = []
    for y in range(center.y + radius, center.y - radius - 1, -1):
        row: list[str] = []
        for x in range(center.x - radius, center.x + radius + 1):
            tile = Tile(x, y)
            row.append(
                _tile_glyph(
                    tile,
                    observation=observation,
                    objects=objects,
                    players=players,
                    blocked=blocked,
                    avoided=avoided,
                    path_tiles=path_tiles,
                    follow_target=follow_target,
                    leader_tile=leader_tile,
                    collect_target=collect_target,
                    camp_fire=camp_fire,
                    camp_slots=camp_slots,
                )
            )
        lines.append("".join(row))

    labels = _object_labels(
        observation,
        blocked=blocked,
        max_labels=cfg.max_object_labels,
    )
    legend = "B=bot L=leader T=target C=collect F=fire 1-8=camp *=path #=blocker !=danger f=food o=object p=player"
    if labels:
        return "\n".join([*lines, legend, *labels])
    return "\n".join([*lines, legend])


def _tile_glyph(
    tile: Tile,
    *,
    observation: Observation,
    objects: dict[Tile, Any],
    players: dict[Tile, Any],
    blocked: set[Tile],
    avoided: set[Tile],
    path_tiles: set[Tile],
    follow_target: Tile | None,
    leader_tile: Tile | None,
    collect_target: Tile | None,
    camp_fire: Tile | None = None,
    camp_slots: dict[Tile, int] | None = None,
) -> str:
    if tile == observation.self.tile:
        return "B"
    if camp_slots is not None:
        slot_id = camp_slots.get(tile)
        if slot_id is not None:
            return str(slot_id)
    if camp_fire is not None and tile == camp_fire:
        return "F"
    if leader_tile is not None and tile == leader_tile:
        return "L"
    if follow_target is not None and tile == follow_target:
        return "T"
    if collect_target is not None and tile == collect_target:
        return "C"
    if tile in players:
        return "p"
    if tile in path_tiles:
        return "*"
    if tile in avoided:
        return "!"
    if tile in blocked:
        return "#"
    obj = objects.get(tile)
    if obj is not None:
        return "f" if obj.food_value > 0 else "o"
    return "."


def _object_labels(
    observation: Observation,
    *,
    blocked: set[Tile],
    max_labels: int,
) -> list[str]:
    nearby = sorted(
        observation.nearby_objects,
        key=lambda obj: (observation.self.tile.distance_to(obj.tile), obj.tile.x, obj.tile.y),
    )
    labels: list[str] = []
    for obj in nearby:
        if len(labels) >= max_labels:
            break
        marker = "blocker" if obj.tile in blocked else "object"
        if obj.food_value > 0:
            marker = f"food:{obj.food_value}"
        labels.append(f"{obj.tile.x},{obj.tile.y}: {obj.name} ({marker})")
    return labels


def _tile_set(raw: Any) -> set[Tile]:
    return set(_tile_sequence(raw))


def _tile_sequence(raw: Any) -> tuple[Tile, ...]:
    if not isinstance(raw, (tuple, list)):
        return ()
    tiles: list[Tile] = []
    for item in raw:
        tile = _fact_tile(item)
        if tile is not None:
            tiles.append(tile)
            continue
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            try:
                tiles.append(Tile(int(item[0]), int(item[1])))
            except (TypeError, ValueError):
                continue
    return tuple(tiles)


def _fact_tile(raw: Any) -> Tile | None:
    if not isinstance(raw, dict):
        return None
    x = raw.get("x")
    y = raw.get("y")
    if x is None or y is None:
        return None
    try:
        return Tile(int(x), int(y))
    except (TypeError, ValueError):
        return None


def _camp_slot_tiles(raw: Any) -> dict[Tile, int]:
    if not isinstance(raw, dict):
        return {}
    slots_raw = raw.get("slots")
    if not isinstance(slots_raw, tuple):
        return {}
    mapping: dict[Tile, int] = {}
    for entry in slots_raw:
        if not isinstance(entry, dict):
            continue
        tile_raw = entry.get("tile")
        slot_id = entry.get("slot_id")
        tile = _fact_tile(tile_raw)
        if tile is None or not isinstance(slot_id, int):
            continue
        mapping[tile] = slot_id
    return mapping
