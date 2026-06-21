from __future__ import annotations


def normalize_item_name(name: str) -> str:
    return name.strip().lower()


def is_loose_stone_name(name: str) -> bool:
    normalized = normalize_item_name(name)
    return normalized in {"stone", "round stone"}


def is_big_hard_rock_name(name: str) -> bool:
    return normalize_item_name(name) == "big hard rock"


def is_sharp_stone_name(name: str) -> bool:
    normalized = normalize_item_name(name)
    return normalized in {"sharp stone", "sharpstone"}
