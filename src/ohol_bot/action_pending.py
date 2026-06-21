from __future__ import annotations

from dataclasses import dataclass, field

from .model import Tile

_DEFAULT_SENT_TICK = -10_000


@dataclass
class PendingAction:
    tile: Tile | None = None
    sent_tick: int = _DEFAULT_SENT_TICK
    attempts: int = field(default=0, repr=False)

    def clear(self) -> None:
        self.tile = None
        self.sent_tick = _DEFAULT_SENT_TICK
        self.attempts = 0

    def note_attempt(self, tick: int, tile: Tile | None = None) -> None:
        if tile is not None and self.tile != tile:
            self.tile = tile
            self.attempts = 0
        elif tile is not None:
            self.tile = tile
        self.attempts += 1
        self.sent_tick = tick

    def settle_reason(
        self,
        now_tick: int,
        settle_ticks: int,
        label: str,
    ) -> str | None:
        if self.tile is None:
            return None
        remaining = settle_ticks - (now_tick - self.sent_tick)
        if remaining > 0:
            return f"{label} settle wait {remaining}"
        return None

    def retry_reason(
        self,
        now_tick: int,
        cooldown_ticks: int,
        label: str,
        *,
        tile: Tile | None = None,
    ) -> str | None:
        if tile is not None and self.tile != tile:
            return None
        if self.tile is None:
            return None
        remaining = cooldown_ticks - (now_tick - self.sent_tick)
        if remaining > 0:
            return f"{label} retry wait {remaining}"
        return None
