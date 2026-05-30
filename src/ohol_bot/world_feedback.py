from __future__ import annotations

from dataclasses import dataclass, field

from .model import Tile


@dataclass(slots=True)
class ActionFeedbackState:
    """Planner/action feedback state separate from packet-derived world model."""

    eat_pending: bool = False
    eat_wait_ticks: int = 0
    eat_started_food_store: int = 0
    pending_force_tile: Tile | None = None
    last_outgoing_move_seq: int = 0
    confirmed_move_seq: int = 0
    pending_move_step: Tile | None = None
    blocked_tiles: set[Tile] = field(default_factory=set)
    avoid_targets: set[Tile] = field(default_factory=set)
    blocked_target_attempts: dict[Tile, int] = field(default_factory=dict)
    last_move_target: Tile | None = None

    @property
    def eat_pending_facts_value(self) -> bool:
        return self.eat_pending

    def note_move_sent(self, step: Tile, target: Tile, sequence: int) -> None:
        self.last_outgoing_move_seq = sequence
        self.pending_move_step = step
        self.last_move_target = target

    def note_force_truncation(self) -> None:
        if self.pending_move_step is not None:
            self.blocked_tiles.add(self.pending_move_step)
        if self.last_move_target is not None:
            self.blocked_tiles.add(self.last_move_target)
            self.avoid_targets.add(self.last_move_target)
        self.pending_move_step = None
        self.last_outgoing_move_seq = 0

    def note_move_blocked(self, target: Tile) -> None:
        attempts = self.blocked_target_attempts.get(target, 0) + 1
        self.blocked_target_attempts[target] = attempts
        if attempts >= 2:
            self.avoid_targets.add(target)

    def note_move_step_failed(self) -> None:
        if self.pending_move_step is not None:
            self.blocked_tiles.add(self.pending_move_step)
        self.pending_move_step = None
        self.last_outgoing_move_seq = 0

    def move_in_flight(self) -> bool:
        return (
            self.last_outgoing_move_seq > 0
            and self.confirmed_move_seq < self.last_outgoing_move_seq
        )

    def take_pending_force(self) -> Tile | None:
        tile = self.pending_force_tile
        self.pending_force_tile = None
        return tile

    def clear_eat_pending(self) -> None:
        self.eat_pending = False
        self.eat_wait_ticks = 0

    def note_use_self(self, current_food_store: int) -> None:
        self.eat_pending = True
        self.eat_wait_ticks = 0
        self.eat_started_food_store = current_food_store

    def maybe_clear_eat_pending_on_food_change(self, food_store: int) -> None:
        if self.eat_pending and food_store > self.eat_started_food_store:
            self.clear_eat_pending()

    def tick_eat_pending(self, timeout_ticks: int) -> None:
        if not self.eat_pending:
            return
        self.eat_wait_ticks += 1
        if self.eat_wait_ticks >= timeout_ticks:
            self.clear_eat_pending()

    def note_move_confirmed(self, done_moving_seq: int) -> bool:
        self.confirmed_move_seq = done_moving_seq
        if done_moving_seq == self.last_outgoing_move_seq:
            self.pending_move_step = None
            return True
        return False

    def note_force_position(self, tile: Tile, done_moving_seq: int) -> None:
        self.note_force_truncation()
        self.pending_force_tile = tile
        self.confirmed_move_seq = done_moving_seq
