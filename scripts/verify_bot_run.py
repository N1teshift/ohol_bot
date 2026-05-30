"""Run the live bot for a bounded time and fail if it gets stuck."""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ohol_bot.model import ActionType, Tile
from ohol_bot.planner import SurvivalPlanner
from ohol_bot.protocol_client import OholProtocolClient, ProtocolCredentials


def main() -> int:
    max_ticks = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    client = OholProtocolClient(
        credentials=ProtocolCredentials(
            email="bot_001@local",
            account_key="aaaa",
            client_id="client_mariusbottest",
            server_password="testPassword",
        ),
        game_data_root=str(ROOT / ".ohol_runtime" / "server"),
    )
    planner = SurvivalPlanner()

    client.login()
    client.frame_paced = True

    positions: list[Tile] = []
    move_targets: list[Tile] = []
    unchanged_ticks = 0
    prev_tile: Tile | None = None
    survived = True
    ticks = 0

    log_path = ROOT / ".ohol_runtime" / "server" / "log.txt"
    log_offset = log_path.stat().st_size if log_path.exists() else 0

    start = time.monotonic()
    try:
        for tick in range(max_ticks):
            if not client.wait_for_frame():
                continue
            observation = client.observe()
            tile = observation.self.tile
            positions.append(tile)

            if prev_tile is not None and tile == prev_tile:
                unchanged_ticks += 1
            else:
                unchanged_ticks = 0
            prev_tile = tile

            if observation.self.max_food_store > 0 and observation.self.food_store <= 0:
                survived = False
                break

            action = planner.decide(observation)
            if action.type is ActionType.MOVE_TO:
                move_targets.append(Tile(action.payload["x"], action.payload["y"]))
            client.send(action)
            ticks += 1
    except ConnectionError:
        print(json.dumps({"ok": False, "reason": "connection_error"}, indent=2))
        return 1
    finally:
        client.close()

    target_counts = Counter(move_targets)
    most_common_target, repeat_count = (
        target_counts.most_common(1)[0] if target_counts else (None, 0)
    )
    unique_positions = len(set(positions))

    log_path = ROOT / ".ohol_runtime" / "server" / "log.txt"
    recent_log = ""
    if log_path.exists():
        with log_path.open("rb") as handle:
            handle.seek(log_offset)
            recent_log = handle.read().decode("utf-8", errors="replace")

    invalid_paths = recent_log.count("Path submitted by player not valid")
    force_ignored = recent_log.count("waiting for FORCE ack")
    flooding = recent_log.count("Message flooding detected")

    stuck_in_place = unchanged_ticks >= 40
    spam_same_target = repeat_count >= 80
    ok = (
        not stuck_in_place
        and not spam_same_target
        and invalid_paths <= 8
        and force_ignored <= 2
        and flooding == 0
        and unique_positions >= 8
    )

    report = {
        "ok": ok,
        "survived": survived,
        "ticks": ticks,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "unique_positions": unique_positions,
        "unchanged_ticks_at_end": unchanged_ticks,
        "final_tile": {"x": prev_tile.x, "y": prev_tile.y} if prev_tile else None,
        "server_frames": client.server_frames,
        "move_actions": len(move_targets),
        "most_repeated_move_target": (
            {"x": most_common_target.x, "y": most_common_target.y, "count": repeat_count}
            if most_common_target is not None
            else None
        ),
        "server_log_signals": {
            "invalid_paths": invalid_paths,
            "force_ignored": force_ignored,
            "flooding": flooding,
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
