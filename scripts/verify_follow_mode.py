"""Run a live follow-mode check against a known leader player id."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ohol_bot.map_debug import MapRenderConfig, render_observation_map
from ohol_bot.model import ActionType, Tile
from ohol_bot.movement_policy import MovementFollowPolicy
from ohol_bot.protocol_client import OholProtocolClient, ProtocolCredentials


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/verify_follow_mode.py <leader_player_id> [max_ticks]")
        return 2
    leader_id = int(sys.argv[1])
    max_ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    client = OholProtocolClient(
        credentials=ProtocolCredentials(
            email="bot_001@local",
            account_key="aaaa",
            client_id="client_mariusbottest",
            server_password="testPassword",
        ),
        game_data_root=str(ROOT / ".ohol_runtime" / "server"),
    )
    policy = MovementFollowPolicy()
    policy.mode = "follow"
    policy.leader_id = leader_id

    distances: list[int] = []
    positions: list[Tile] = []
    move_actions = 0
    leader_seen_ticks = 0
    stagnant_ticks = 0
    best_distance: int | None = None
    diagnostic_snapshots: list[dict[str, object]] = []
    start = time.monotonic()

    client.login()
    client.frame_paced = True
    try:
        for _ in range(max_ticks):
            if not client.wait_for_frame():
                continue
            observation = client.observe()
            action = policy.decide(observation)
            positions.append(observation.self.tile)
            distance = observation.facts.get("follow_leader_distance")
            if isinstance(distance, int):
                distances.append(distance)
                leader_seen_ticks += 1
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    stagnant_ticks = 0
                else:
                    stagnant_ticks += 1
                if stagnant_ticks in {20, 40, 80}:
                    diagnostic_snapshots.append(
                        {
                            "tick": len(positions),
                            "distance": distance,
                            "self_tile": {
                                "x": observation.self.tile.x,
                                "y": observation.self.tile.y,
                            },
                            "leader_tile": observation.facts.get("follow_leader_tile"),
                            "follow_target": observation.facts.get("follow_target"),
                            "path_diagnostics": observation.facts.get(
                                "last_path_diagnostics",
                            ),
                            "candidate_tiles": observation.facts.get(
                                "follow_candidate_tiles",
                            ),
                            "map": render_observation_map(
                                observation,
                                config=MapRenderConfig(radius=8, max_object_labels=6),
                            ),
                        }
                    )
            if action.type is ActionType.MOVE_TO:
                move_actions += 1
            client.send(action)
    except ConnectionError:
        print(json.dumps({"ok": False, "reason": "connection_error"}, indent=2))
        return 1
    finally:
        client.close()

    adjacent_ticks = sum(1 for distance in distances if distance <= 1)
    ok = leader_seen_ticks > 0 and adjacent_ticks >= max(1, leader_seen_ticks // 2)
    report = {
        "ok": ok,
        "leader_id": leader_id,
        "ticks": len(positions),
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "leader_seen_ticks": leader_seen_ticks,
        "adjacent_follow_ticks": adjacent_ticks,
        "move_actions": move_actions,
        "unique_positions": len(set(positions)),
        "final_tile": (
            {"x": positions[-1].x, "y": positions[-1].y} if positions else None
        ),
        "final_distance": distances[-1] if distances else None,
        "server_frames": client.server_frames,
        "diagnostic_snapshots": diagnostic_snapshots[-3:],
    }
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
