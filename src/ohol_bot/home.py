from __future__ import annotations

from typing import TYPE_CHECKING

from .danger import base_object_name
from .model import ObjectState, Observation, Tile

if TYPE_CHECKING:
    from .game_data import OholGameData

# Tiles around the home center (well/spring) that still count as "at home".
DEFAULT_HOME_AREA_RADIUS = 12

# How far from the speaker to search for a well/spring when setting home.
HOME_CENTER_SEARCH_RADIUS = 16


def is_home_center_name(name: str) -> bool:
    """True for wells, natural springs, and close OHOL name variants."""
    base = base_object_name(name)
    if base == "home marker":
        return True
    if "natural spring" in base:
        return True
    if "gradient dry spring" in base:
        return True
    if base.startswith("well site"):
        return True
    if base.startswith("shallow well") or base.startswith("deep well"):
        return True
    if base == "hot spring" or base.startswith("sulfur-free hot spring"):
        return True
    return False


def is_home_center_object(
    obj: ObjectState,
    game_data: OholGameData | None = None,
) -> bool:
    if game_data is not None:
        record = game_data.objects.get(obj.object_id)
        if record is not None and record.home_marker:
            return True
    return is_home_center_name(obj.name)


def _home_center_priority(name: str) -> int:
    base = base_object_name(name)
    if "natural spring" in base or "gradient dry spring" in base:
        return 0
    if base.startswith("well site"):
        return 1
    if base.startswith("shallow well") or base.startswith("deep well"):
        return 2
    if "hot spring" in base:
        return 3
    if base == "home marker":
        return 4
    return 5


def find_home_center_near(
    observation: Observation,
    origin: Tile,
    *,
    game_data: OholGameData | None = None,
    max_radius: int = HOME_CENTER_SEARCH_RADIUS,
) -> ObjectState | None:
    """Nearest well/spring/home-marker object within radius of origin."""
    candidates: list[tuple[int, int, ObjectState]] = []
    for obj in observation.nearby_objects:
        if not is_home_center_object(obj, game_data):
            continue
        distance = _chebyshev(origin, obj.tile)
        if distance > max_radius:
            continue
        candidates.append(
            (distance, _home_center_priority(obj.name), obj),
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2].tile.x, item[2].tile.y))
    return candidates[0][2]


def home_area_radius(observation: Observation) -> int:
    if observation.home_radius is not None and observation.home_radius > 0:
        return observation.home_radius
    raw = observation.facts.get("home_radius")
    if isinstance(raw, int) and raw > 0:
        return raw
    if observation.home is not None:
        return DEFAULT_HOME_AREA_RADIUS
    return DEFAULT_HOME_AREA_RADIUS


def is_at_home(
    observation: Observation,
    tile: Tile | None = None,
    *,
    radius: int | None = None,
) -> bool:
    if observation.home is None:
        return False
    position = tile if tile is not None else observation.self.tile
    limit = radius if radius is not None else home_area_radius(observation)
    return _chebyshev(position, observation.home) <= limit


def _chebyshev(a: Tile, b: Tile) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))
