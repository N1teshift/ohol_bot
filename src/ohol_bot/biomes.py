from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .model import Tile

DEFAULT_BIOME_NAMES: dict[int, str] = {
    0: "Grasslands",
    1: "Yellow Prairies",
    2: "Swamps",
    3: "Badlands",
    4: "Tundra",
    5: "Desert",
    6: "Jungle",
}


@dataclass(frozen=True, slots=True)
class BiomeCatalog:
    names: dict[int, str]
    order: tuple[int, ...] = ()
    special_biome_ids: frozenset[int] = frozenset()

    def biome_name(self, biome_id: int) -> str:
        return self.names.get(biome_id, f"Biome {biome_id}")


def load_biome_catalog(root: str | Path) -> BiomeCatalog:
    root_path = Path(root)
    settings_path = root_path / "contentSettings"
    names = dict(DEFAULT_BIOME_NAMES)
    order = _load_int_lines(settings_path / "biomeOrder.ini")
    special = frozenset(_load_int_lines(settings_path / "specialBiomes.ini"))
    return BiomeCatalog(names=names, order=order, special_biome_ids=special)


def count_biomes_in_radius(
    tile_biomes: dict[Tile, int],
    center: Tile,
    radius: int,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for tile, biome_id in tile_biomes.items():
        if center.distance_to(tile) > radius:
            continue
        counts[biome_id] = counts.get(biome_id, 0) + 1
    return counts


def nearest_tile_with_biome(
    tile_biomes: dict[Tile, int],
    center: Tile,
    biome_id: int,
    *,
    max_radius: int | None = None,
) -> Tile | None:
    best: Tile | None = None
    best_distance: int | None = None
    for tile, seen_biome_id in tile_biomes.items():
        if seen_biome_id != biome_id:
            continue
        distance = center.distance_to(tile)
        if max_radius is not None and distance > max_radius:
            continue
        if best_distance is None or distance < best_distance:
            best = tile
            best_distance = distance
    return best


def biomes_likely_for_object(
    object_spawn_biomes: frozenset[int],
    catalog: BiomeCatalog,
) -> tuple[str, ...]:
    if not object_spawn_biomes:
        return ()
    return tuple(catalog.biome_name(biome_id) for biome_id in sorted(object_spawn_biomes))


def _load_int_lines(path: Path) -> tuple[int, ...]:
    if not path.exists():
        return ()
    values: list[int] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            values.append(int(stripped))
        except ValueError:
            continue
    return tuple(values)
