from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Tile

# Eight tiles north of the well/home center (matches manual_control north = (0, 1)).
FIRE_OFFSET = Tile(0, 8)

# Ring offsets clockwise from NW around the fire center tile.
_SLOT_OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, 1),  # 1 NW
    (0, 1),  # 2 N
    (1, 1),  # 3 NE
    (1, 0),  # 4 E
    (1, -1),  # 5 SE
    (0, -1),  # 6 S
    (-1, -1),  # 7 SW
    (-1, 0),  # 8 W
)

# slot_id, item_query, desired_count
CAMP_SLOT_ITEMS: tuple[tuple[int, str, int], ...] = (
    (1, "stone", 10),
    (2, "sharp stone", 6),
    (3, "flint", 6),
    (4, "wild onion", 6),
    (5, "wild carrot", 6),
    (6, "burdock", 6),
    (7, "wild garlic", 6),
    (8, "straight branch", 6),
)


@dataclass(frozen=True, slots=True)
class CampSlotSpec:
    slot_id: int
    tile: Tile
    item_query: str
    desired_count: int


@dataclass(frozen=True, slots=True)
class CampLayout:
    home_tile: Tile
    fire_tile: Tile
    slots: tuple[CampSlotSpec, ...]


def slot_offsets_clockwise_from_nw() -> tuple[tuple[int, int], ...]:
    return _SLOT_OFFSETS


def build_camp_layout(home_tile: Tile) -> CampLayout:
    fire_tile = Tile(
        home_tile.x + FIRE_OFFSET.x,
        home_tile.y + FIRE_OFFSET.y,
    )
    slots: list[CampSlotSpec] = []
    for (offset, spec) in zip(_SLOT_OFFSETS, CAMP_SLOT_ITEMS, strict=True):
        slot_id, item_query, desired_count = spec
        dx, dy = offset
        slots.append(
            CampSlotSpec(
                slot_id=slot_id,
                tile=Tile(fire_tile.x + dx, fire_tile.y + dy),
                item_query=item_query,
                desired_count=desired_count,
            )
        )
    return CampLayout(home_tile=home_tile, fire_tile=fire_tile, slots=tuple(slots))


def camp_layout_to_facts(layout: CampLayout) -> dict[str, Any]:
    return {
        "home_tile": {"x": layout.home_tile.x, "y": layout.home_tile.y},
        "fire_tile": {"x": layout.fire_tile.x, "y": layout.fire_tile.y},
        "slots": tuple(
            {
                "slot_id": slot.slot_id,
                "tile": {"x": slot.tile.x, "y": slot.tile.y},
                "item_query": slot.item_query,
                "desired_count": slot.desired_count,
            }
            for slot in layout.slots
        ),
    }


def camp_layout_from_facts(raw: Any) -> CampLayout | None:
    if not isinstance(raw, dict):
        return None
    home_raw = raw.get("home_tile")
    fire_raw = raw.get("fire_tile")
    slots_raw = raw.get("slots")
    if not isinstance(home_raw, dict) or not isinstance(fire_raw, dict):
        return None
    if not isinstance(slots_raw, tuple):
        return None
    try:
        home_tile = Tile(int(home_raw["x"]), int(home_raw["y"]))
        fire_tile = Tile(int(fire_raw["x"]), int(fire_raw["y"]))
    except (KeyError, TypeError, ValueError):
        return None
    slots: list[CampSlotSpec] = []
    for entry in slots_raw:
        if not isinstance(entry, dict):
            return None
        try:
            slots.append(
                CampSlotSpec(
                    slot_id=int(entry["slot_id"]),
                    tile=Tile(int(entry["tile"]["x"]), int(entry["tile"]["y"])),
                    item_query=str(entry["item_query"]),
                    desired_count=int(entry["desired_count"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None
    if not slots:
        return None
    return CampLayout(home_tile=home_tile, fire_tile=fire_tile, slots=tuple(slots))
