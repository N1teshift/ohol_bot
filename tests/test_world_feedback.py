from ohol_bot.model import Tile
from ohol_bot.world_feedback import ActionFeedbackState


def test_note_move_blocked_adds_to_blocked_tiles_not_avoid() -> None:
    feedback = ActionFeedbackState()
    target = Tile(3, 4)

    feedback.note_move_blocked(target)
    assert target not in feedback.blocked_tiles

    feedback.note_move_blocked(target)
    assert target in feedback.blocked_tiles


def test_note_force_truncation_does_not_add_avoid_targets() -> None:
    feedback = ActionFeedbackState()
    feedback.note_move_sent(
        Tile(1, 0),
        Tile(5, 0),
        sequence=1,
        path=(Tile(1, 0), Tile(2, 0)),
    )

    feedback.note_force_truncation()

    assert Tile(5, 0) in feedback.blocked_tiles
    assert Tile(1, 0) in feedback.blocked_tiles
    assert Tile(2, 0) in feedback.blocked_tiles


def test_note_move_confirmed_clears_last_move_target() -> None:
    feedback = ActionFeedbackState()
    feedback.note_move_sent(Tile(1, 0), Tile(4, 0), sequence=7)

    assert feedback.note_move_confirmed(7) is True
    assert feedback.last_move_target is None
