from pathlib import Path

from ohol_bot.game_data import load_game_data
from ohol_bot.harvest import build_harvest_catalog, merge_harvest_into_stack_rule


def test_build_harvest_catalog_includes_burdock_and_carrot() -> None:
    root = Path(".ohol_runtime/server")
    if not (root / "objects").exists():
        return

    game_data = load_game_data(root)
    catalog = build_harvest_catalog(game_data)
    by_query = {rule["query"]: rule for rule in catalog}

    assert "burdock" in by_query
    assert "wild carrot" in by_query
    assert "flint" in by_query
    assert by_query["burdock"].get("product_object_id") == 807
    assert 34 in by_query["burdock"]["tool_object_ids"]


def test_merge_harvest_into_stack_rule_updates_loose_object_id() -> None:
    root = Path(".ohol_runtime/server")
    if not (root / "objects").exists():
        return

    game_data = load_game_data(root)
    harvest_catalog = build_harvest_catalog(game_data)
    merged = merge_harvest_into_stack_rule(
        {
            "display_name": "Burdock",
            "loose_names": ("burdock",),
            "pile_names": ("pile of burdock roots",),
            "loose_object_id": 804,
            "query_aliases": ("burdock",),
        },
        harvest_catalog,
    )

    assert merged.get("harvest") is not None
    assert merged["loose_object_id"] == 807
    assert merged["display_name"] == "Burdock Root"
    assert "burdock root" in merged["item_names"]
    assert "burdock" not in merged["item_names"]
