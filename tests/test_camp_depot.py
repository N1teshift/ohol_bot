from ohol_bot.camp_depot import (
    CAMP_SLOT_ITEMS,
    FIRE_OFFSET,
    build_camp_layout,
    camp_layout_from_facts,
    camp_layout_to_facts,
    slot_offsets_clockwise_from_nw,
)
from ohol_bot.model import Tile


def test_fire_offset_is_eight_tiles_north() -> None:
    assert FIRE_OFFSET == Tile(0, 8)


def test_slot_offsets_clockwise_from_northwest() -> None:
    assert slot_offsets_clockwise_from_nw() == (
        (-1, 1),
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, -1),
        (-1, 0),
    )


def test_build_camp_layout_from_home_tile() -> None:
    home = Tile(10, 20)
    layout = build_camp_layout(home)

    assert layout.home_tile == home
    assert layout.fire_tile == Tile(10, 28)
    assert len(layout.slots) == 8
    assert layout.slots[0].slot_id == 1
    assert layout.slots[0].tile == Tile(9, 29)
    assert layout.slots[0].item_query == "stone"
    assert layout.slots[0].desired_count == 10
    assert layout.slots[7].slot_id == 8
    assert layout.slots[7].tile == Tile(9, 28)
    assert layout.slots[7].item_query == "straight branch"
    assert layout.slots[7].desired_count == 6


def test_camp_slot_items_cover_eight_slots() -> None:
    assert len(CAMP_SLOT_ITEMS) == 8
    assert [slot_id for slot_id, _, _ in CAMP_SLOT_ITEMS] == list(range(1, 9))


def test_camp_layout_round_trip_facts() -> None:
    layout = build_camp_layout(Tile(3, 4))
    facts = camp_layout_to_facts(layout)
    restored = camp_layout_from_facts(facts)

    assert restored is not None
    assert restored.fire_tile == layout.fire_tile
    assert restored.slots == layout.slots
