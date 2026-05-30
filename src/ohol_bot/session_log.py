from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model import Action
from .runner import EpisodeResult

DEFAULT_SESSION_LOG_PATH = Path(".ohol_runtime/logs/last_run.json")
MAX_ACTIONS_IN_LOG = 2000
MAX_LOG_BYTES = 2_000_000


def action_to_dict(action: Action) -> dict[str, Any]:
    return {"type": action.type.value, "payload": dict(action.payload)}


def build_episode_report(
    result: EpisodeResult,
    *,
    max_actions: int = MAX_ACTIONS_IN_LOG,
) -> dict[str, Any]:
    total = len(result.actions)
    if total <= max_actions:
        saved = [action_to_dict(action) for action in result.actions]
        omitted = 0
    else:
        tail = result.actions[-max_actions:]
        saved = [action_to_dict(action) for action in tail]
        omitted = total - len(tail)

    return {
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "stopped_by": result.stop_reason,
        "survived": result.survived,
        "ticks": result.ticks,
        "metrics": dict(result.metrics),
        "actions_total": total,
        "actions_saved": len(saved),
        "actions_omitted": omitted,
        "actions": saved,
    }


def write_session_log(
    report: dict[str, Any],
    path: Path | str = DEFAULT_SESSION_LOG_PATH,
    *,
    max_bytes: int = MAX_LOG_BYTES,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(report)
    while True:
        text = json.dumps(payload, indent=2)
        if len(text.encode("utf-8")) <= max_bytes:
            destination.write_text(text, encoding="utf-8")
            return destination

        actions = payload.get("actions")
        if not isinstance(actions, list) or len(actions) <= 100:
            destination.write_text(text[:max_bytes], encoding="utf-8")
            return destination

        keep = max(100, len(actions) // 2)
        payload["actions"] = actions[-keep:]
        payload["actions_saved"] = keep
        payload["actions_omitted"] = int(payload.get("actions_total", keep)) - keep
        payload["log_truncated_for_size"] = True


def terminal_summary(report: dict[str, Any], log_path: Path) -> str:
    lines = [
        "Session ended.",
        f"  survived={report['survived']}  ticks={report['ticks']}  "
        f"stopped_by={report.get('stopped_by', 'normal')}",
        f"  actions: {report['actions_total']} total, "
        f"{report['actions_saved']} saved"
        + (
            f", {report['actions_omitted']} omitted from log"
            if report.get("actions_omitted", 0) > 0
            else ""
        ),
        f"  log: {log_path.resolve()}",
    ]
    if report.get("log_truncated_for_size"):
        lines.append("  (log was shortened to stay under size limit)")
    return "\n".join(lines)


def finish_run_live_session(
    result: EpisodeResult,
    *,
    watch: bool,
    log_path: Path | str = DEFAULT_SESSION_LOG_PATH,
    max_actions: int = MAX_ACTIONS_IN_LOG,
    print_summary: bool = True,
) -> Path:
    report = build_episode_report(result, max_actions=max_actions)
    written = write_session_log(report, log_path)
    if watch and result.last_dashboard:
        from .dashboard import DashboardFrame, print_dashboard_snapshot

        print()
        print("--- Final dashboard snapshot ---")
        print_dashboard_snapshot(DashboardFrame(result.last_dashboard))
    if watch:
        print()
    if print_summary:
        print(terminal_summary(report, written))
    return written
