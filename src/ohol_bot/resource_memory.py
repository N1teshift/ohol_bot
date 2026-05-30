from __future__ import annotations

BRANCH_NAMES = frozenset({"straight branch", "curved branch"})


def is_tree_like_name(name: str) -> bool:
    """True for map trees that may yield branches (not tools or dead variants)."""
    if not name.endswith(" Tree"):
        return False
    if name.startswith("@"):
        return False
    if name.startswith("Dead "):
        return False
    if name.startswith("Spent "):
        return False
    return True


def matches_collect_landmark(name: str) -> bool:
    return name in BRANCH_NAMES or is_tree_like_name(name)


def is_priority_landmark(name: str, food_value: int) -> bool:
    """Food and branch/tree landmarks are evicted last from long-term memory."""
    if food_value > 0:
        return True
    return matches_collect_landmark(name)
