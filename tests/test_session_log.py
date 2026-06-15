import json
from pathlib import Path

from ohol_bot.model import Action, ActionType
from ohol_bot.runner import EpisodeResult
from ohol_bot.session_log import (
    MAX_LOG_BYTES,
    build_episode_report,
    terminal_summary,
    write_session_log,
)


def test_build_episode_report_truncates_action_tail() -> None:
    actions = tuple(
        Action(ActionType.WAIT, {"ticks": 1}) for _ in range(10)
    )
    result = EpisodeResult(
        ticks=10,
        actions=actions,
        survived=True,
        metrics={},
        stop_reason="keyboard_interrupt",
    )

    report = build_episode_report(result, max_actions=4)

    assert report["actions_total"] == 10
    assert report["actions_saved"] == 4
    assert report["actions_omitted"] == 6
    assert len(report["actions"]) == 4
    assert report["stopped_by"] == "keyboard_interrupt"


def test_write_session_log_overwrites_and_respects_size(tmp_path: Path) -> None:
    actions = tuple(
        Action(ActionType.SAY, {"text": "x" * 200}) for _ in range(500)
    )
    result = EpisodeResult(
        ticks=500,
        actions=actions,
        survived=True,
        metrics={"final_x": 1.0},
    )
    report = build_episode_report(result, max_actions=500)
    log_path = tmp_path / "last_run.json"

    write_session_log(report, log_path, max_bytes=MAX_LOG_BYTES)
    first_size = log_path.stat().st_size
    assert first_size <= MAX_LOG_BYTES

    write_session_log({"survived": False, "ticks": 1, "actions": []}, log_path)
    second = json.loads(log_path.read_text(encoding="utf-8"))
    assert second["survived"] is False

    summary = terminal_summary(report, log_path)
    assert "Session ended" in summary
    assert str(log_path.resolve()) in summary


def test_build_episode_report_includes_events_when_present() -> None:
    result = EpisodeResult(
        ticks=2,
        actions=(Action(ActionType.WAIT, {"ticks": 1}),),
        survived=True,
        metrics={},
        events=(
            {"tick": 0, "event": "manual_plan_move", "steps": 10},
            {"tick": 1, "event": "manual_plan_cancelled"},
        ),
    )

    report = build_episode_report(result, max_actions=10)

    assert report["events_total"] == 2
    assert len(report["events"]) == 2
    assert report["events"][0]["event"] == "manual_plan_move"
