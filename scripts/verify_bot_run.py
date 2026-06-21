"""Run the live bot for a bounded time and fail if it gets stuck."""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ohol_bot.model import Action, ActionType, Observation, Tile
from ohol_bot.protocol_client import OholProtocolClient, ProtocolCredentials

DEFAULT_SECONDS = 15.0
REFERENCE_SECONDS = 60.0
FRAME_WAIT_SECONDS = 3.0
NO_FRAME_ABORT_SECONDS = 10.0


class MovementSmokePolicy:
    def decide(self, observation: Observation) -> Action:
        offsets = (
            (1, 0),
            (1, 0),
            (0, 1),
            (-1, 0),
            (-1, 0),
            (0, -1),
            (1, 1),
            (-1, -1),
        )
        dx, dy = offsets[observation.tick % len(offsets)]
        tile = observation.self.tile
        return Action(ActionType.MOVE_TO, {"x": tile.x + dx, "y": tile.y + dy})


def scaled_thresholds(max_seconds: float) -> dict[str, int]:
    scale = max(0.25, max_seconds / REFERENCE_SECONDS)
    return {
        "stuck_consecutive": max(5, int(40 * scale)),
        "spam_repeat": max(10, int(80 * scale)),
        "min_unique_positions": max(3, int(8 * scale)),
        "invalid_paths": max(2, int(8 * scale)),
        "force_ignored": max(1, int(2 * scale)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Movement smoke test against the private server.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_SECONDS,
        help=f"Wall-clock run limit (default: {DEFAULT_SECONDS:g})",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Optional tick cap (whichever limit is hit first)",
    )
    parser.add_argument(
        "legacy_max_ticks",
        nargs="?",
        type=int,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def resolve_limits(args: argparse.Namespace) -> tuple[float, int | None]:
    if args.legacy_max_ticks is not None:
        warnings.warn(
            "Positional max_ticks is deprecated; use --seconds and --max-ticks",
            DeprecationWarning,
            stacklevel=2,
        )
        max_ticks = args.legacy_max_ticks
        # Legacy `verify_bot_run.py 800` needed ~2 minutes at typical frame rates.
        max_seconds = max(max_ticks * 0.15, DEFAULT_SECONDS)
        return max_seconds, max_ticks
    return args.seconds, args.max_ticks


def main() -> int:
    args = parse_args()
    max_seconds, max_ticks = resolve_limits(args)
    thresholds = scaled_thresholds(max_seconds)
    policy = MovementSmokePolicy()

    client = OholProtocolClient(
        credentials=ProtocolCredentials(
            email="bot_001@local",
            account_key="aaaa",
            client_id="client_mariusbottest",
            server_password="testPassword",
        ),
        game_data_root=str(ROOT / ".ohol_runtime" / "server"),
    )

    client.login()
    client.frame_paced = True

    positions: list[Tile] = []
    move_targets: list[Tile] = []
    unchanged_ticks = 0
    prev_tile: Tile | None = None
    survived = True
    ticks = 0
    missed_frames = 0

    log_path = ROOT / ".ohol_runtime" / "server" / "log.txt"
    log_offset = log_path.stat().st_size if log_path.exists() else 0

    start = time.monotonic()
    deadline = start + max_seconds
    try:
        while time.monotonic() < deadline:
            if max_ticks is not None and ticks >= max_ticks:
                break
            if not client.wait_for_frame(timeout_seconds=FRAME_WAIT_SECONDS):
                missed_frames += 1
                if ticks == 0 and time.monotonic() - start >= NO_FRAME_ABORT_SECONDS:
                    print(
                        json.dumps(
                            {
                                "ok": False,
                                "reason": "no_server_frames",
                                "elapsed_seconds": round(
                                    time.monotonic() - start, 2
                                ),
                                "hint": "Start the private server first "
                                "(scripts/run_private_server.ps1)",
                            },
                            indent=2,
                        )
                    )
                    return 1
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

            action = policy.decide(observation)
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

    stuck_in_place = unchanged_ticks >= thresholds["stuck_consecutive"]
    spam_same_target = repeat_count >= thresholds["spam_repeat"]
    ok = (
        ticks > 0
        and not stuck_in_place
        and not spam_same_target
        and invalid_paths <= thresholds["invalid_paths"]
        and force_ignored <= thresholds["force_ignored"]
        and flooding == 0
        and unique_positions >= thresholds["min_unique_positions"]
    )

    report = {
        "ok": ok,
        "survived": survived,
        "ticks": ticks,
        "max_seconds": max_seconds,
        "max_ticks": max_ticks,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "missed_frames": missed_frames,
        "unique_positions": unique_positions,
        "unchanged_ticks_at_end": unchanged_ticks,
        "final_tile": {"x": prev_tile.x, "y": prev_tile.y} if prev_tile else None,
        "server_frames": client.server_frames,
        "move_actions": len(move_targets),
        "thresholds": thresholds,
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
