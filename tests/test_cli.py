from ohol_bot.cli import _build_run_live_policy
from ohol_bot.movement_policy import MovementFollowPolicy


def test_build_run_live_policy_uses_movement_follow_policy() -> None:
    policy = _build_run_live_policy()

    assert isinstance(policy, MovementFollowPolicy)
    assert policy.mode == "idle"
