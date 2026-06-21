from ohol_bot.action_pending import PendingAction
from ohol_bot.model import Tile


def test_pending_action_clear_resets_state() -> None:
    pending = PendingAction(tile=Tile(1, 0), sent_tick=5, attempts=2)
    pending.clear()
    assert pending.tile is None
    assert pending.sent_tick == -10_000
    assert pending.attempts == 0


def test_pending_action_note_attempt_resets_attempts_on_tile_change() -> None:
    pending = PendingAction(tile=Tile(1, 0), sent_tick=1, attempts=3)
    pending.note_attempt(2, Tile(2, 0))
    assert pending.tile == Tile(2, 0)
    assert pending.attempts == 1
    assert pending.sent_tick == 2


def test_pending_action_settle_reason() -> None:
    pending = PendingAction(tile=Tile(0, 0), sent_tick=5)
    assert pending.settle_reason(6, 3, "drop") == "drop settle wait 2"
    assert pending.settle_reason(8, 3, "drop") is None


def test_pending_action_retry_reason_requires_matching_tile() -> None:
    pending = PendingAction(tile=Tile(1, 0), sent_tick=5)
    assert pending.retry_reason(6, 3, "pickup", tile=Tile(2, 0)) is None
    assert pending.retry_reason(6, 3, "pickup", tile=Tile(1, 0)) == "pickup retry wait 2"
