from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path


def shared_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def find_close_name(name: str, names: tuple[str, ...]) -> str:
    """Closest prescribed OHOL name for a spoken token (names.cpp behavior)."""
    if not names:
        return ""
    target = name.strip().upper()
    if not target:
        return ""

    index = bisect.bisect_left(names, target)
    if index < len(names) and names[index] == target:
        return names[index]

    candidates: list[str] = []
    if index < len(names):
        candidates.append(names[index])
    if index > 0:
        candidates.append(names[index - 1])
    if not candidates:
        return names[0]

    return min(
        candidates,
        key=lambda candidate: (
            -shared_prefix_length(target, candidate),
            len(candidate),
        ),
    )


def load_name_list(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    names: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip().upper()
        if line:
            names.append(line)
    names.sort()
    return tuple(names)


@dataclass(frozen=True, slots=True)
class NameCatalog:
    male_first_names: tuple[str, ...]
    female_first_names: tuple[str, ...]
    last_names: tuple[str, ...]

    @classmethod
    def load(cls, game_data_root: Path | str | None) -> NameCatalog:
        if game_data_root is None:
            return cls((), (), ())
        root = Path(game_data_root)
        return cls(
            male_first_names=load_name_list(root / "maleNames.txt"),
            female_first_names=load_name_list(root / "femaleNames.txt"),
            last_names=load_name_list(root / "lastNames.txt"),
        )

    @property
    def available(self) -> bool:
        return bool(self.male_first_names or self.female_first_names or self.last_names)

    def close_first_name(self, raw_name: str, *, female: bool) -> str:
        names = self.female_first_names if female else self.male_first_names
        if not names:
            return raw_name.strip().upper()
        return find_close_name(raw_name, names)

    def close_last_name(self, raw_name: str) -> str:
        if not self.last_names:
            return raw_name.strip().upper()
        return find_close_name(raw_name, self.last_names)


def parse_assigned_name_line(line: str) -> tuple[int, str, str | None] | None:
    """Parse lifeLog/*_names.txt lines: '<player_id> <first> [<family...>]'."""
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    try:
        player_id = int(parts[0])
    except ValueError:
        return None
    first_name = parts[1].upper()
    family_name = " ".join(parts[2:]).upper() if len(parts) > 2 else None
    return player_id, first_name, family_name
