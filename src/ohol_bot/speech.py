from __future__ import annotations

import math


def say_limit_for_age(age: float) -> int:
    """Maximum SAY length for a player at the given age (OHOL sayLimit.cpp)."""
    floor_age = math.floor(age)
    say_cap = int(floor_age + 1)
    adult_base = 50

    if floor_age >= 16:
        say_cap = 16 + (floor_age - 16) // 2 + adult_base
    elif floor_age >= 8:
        extra_age = floor_age - 8
        if extra_age > 0:
            sixteen_limit = adult_base + 16
            full_increase = sixteen_limit - 9
            fraction = extra_age / 8.0
            hardness = 12.0
            curved_fraction = 1.0 / (
                1.0 + math.pow(2.0, -hardness * (fraction - 0.5))
            )
            increase = full_increase * curved_fraction
            say_cap = 9 + math.floor(increase)

    return say_cap


def fit_say_text(text: str, *, age: float) -> str | None:
    """Uppercase speech that fits the age cap, or None if it cannot."""
    cleaned = text.strip().upper()
    if not cleaned:
        return None
    if len(cleaned) <= say_limit_for_age(age):
        return cleaned
    return None


def fit_say_from_candidates(candidates: tuple[str, ...], *, age: float) -> str | None:
    """Pick the longest candidate that still fits the age cap."""
    limit = say_limit_for_age(age)
    for candidate in candidates:
        upper = candidate.strip().upper()
        if upper and len(upper) <= limit:
            return upper
    return None
