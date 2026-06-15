# Agent Onboarding — OHOL Bot

Read **[docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md)** first. It is the full project context document for fresh sessions.

## One-line goal

Build Python bots that play One Hour One Life on a local private server, survive, and eventually cooperate as a family.

## Current focus

**Single live bot** with a movement-first idle/follow loop (`run-live --forever`, `play`). The protocol client stays connected, tracks world state from packets, and runs `MovementFollowPolicy` by default. Legacy survival behavior still exists for scenarios/tests and can forage, pick up, **eat held food via `USE_SELF`**, return home, collect branches, and wait when carried.

**Movement:** one movement decision per server `FM` frame; the client waits until **stationary** before the next action. `MOVE` messages may carry a short batched path (up to 6 offsets, including diagonals). **Obstacle-aware pathfinding** (`movement.py`) routes around `blocksWalking` objects using 8-way BFS, diagonal straight-line prefixes, birth-relative coordinates, corner-cutting rules, and horizontal `leftBlockingRadius` / `rightBlockingRadius` footprints. `blocked_tiles` hard-block walking; `avoid_targets` are hard skips in explore/survival but only a soft penalty for follow formation targets.

**Follow:** in-game `follow` from another player starts following that speaker; `stop follow` / `idle` returns to idle. Follow uses Chebyshev distance: the bot waits when on the leader's tile or adjacent (distance <= 1), and only moves when distance >= 2 toward a walkable tile exactly one step from the leader.

**Verified on private server:** forage → pick up → eat loop (e.g. Gooseberry). Use **`--frame-paced`** for one decision per server `FM` frame. Run **`scripts/verify_bot_run.py`** after movement changes to catch stuck-on-tree regressions.

**Manual control:** `python -m ohol_bot.cli control` — interactive REPL to walk N tiles east/south/etc. without the autopilot planner.

**Not started yet:** recipe/transition planner (sharp stone, fire), multi-bot family coordination.

## Before you code

1. Server must be running: `.\scripts\run_private_server.ps1`
2. Python path: `$env:PYTHONPATH='src'`
3. Do not edit `Program Files` or `.cursor/plans/*.plan.md`
4. Do not git commit unless the user asks
5. After movement/pathfinding changes, run: `python scripts/verify_bot_run.py 800`

## Bot credentials (sandbox)

- email: `bot_001@local`
- account_key: `aaaa`
- client_id: `client_mariusbottest`
- server_password: `testPassword`
- server: `localhost:8005`

## Main files

| File | Role |
|------|------|
| `src/ohol_bot/protocol_client.py` | `OholProtocolClient` — login, read loop, keep-alive, self-id lock, `_action_tile`, MOVE gating, pathfinding hook |
| `src/ohol_bot/world_state.py` | Mutable state from PU/PM/FX/MC/MX → `Observation`; birth tile, move seq, blocked/avoid, held latch, age, stationary |
| `src/ohol_bot/movement.py` | BFS pathfinding, batched diagonal paths, `resolve_approach_tile`, corner-cutting, `blocksWalking`, horizontal wide collision |
| `src/ohol_bot/movement_policy.py` | Idle/follow policy, chat commands, one-tile follow formation |
| `src/ohol_bot/hunger.py` | Hunger threshold, `action_blocker` / eat blockers (age, moving, eat pending) |
| `src/ohol_bot/runner.py` | `run_live_episode` — wall-clock or `--frame-paced` loop |
| `src/ohol_bot/protocol_messages.py` | Packet parser (PU, PM, FX, MC, CM, …); `done_moving_seq` |
| `src/ohol_bot/planner.py` | `SurvivalPlanner` — hunger, home, branches, carried-wait |
| `src/ohol_bot/spatial_memory.py` | Working + long-term object landmarks (absolute); biome_id per tile |
| `src/ohol_bot/resource_memory.py` | Branch/tree landmark matching for collect navigation |
| `src/ohol_bot/skills.py` | Forage, explore, return home, collect; remembered food/branches when out of range |
| `src/ohol_bot/manual_control.py` | Interactive terminal control (`control` CLI) |
| `src/ohol_bot/game_data.py` | Objects/transitions from sandbox |
| `src/ohol_bot/dashboard.py` | Terminal dashboard for `--watch` |
| `src/ohol_bot/cli.py` | `run-live`, `control`, `stay-alive`, `verify-live`, probes |
| `scripts/verify_bot_run.py` | Live smoke test — fails if bot gets stuck (unchanged tile, spam target, invalid paths) |
| `scripts/verify_follow_mode.py` | Live follow smoke test against a known leader player id |
| `config/private_server.json` | Server sandbox settings |
| `config/local_clients.json` | Bot client credentials |

## Run the live bot (two terminals)

**Terminal 1 — server:**

```powershell
.\scripts\run_private_server.ps1
```

**Terminal 2 — bot with dashboard:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --watch
```

Use `--frame-paced` to react once per server `FM` frame (recommended). Use `--tick-seconds N` for slower wall-clock pacing. Use `--forever` to run until Ctrl+C. With `--watch`, Ctrl+C leaves the dashboard visible; a short summary prints and the full run is overwritten to `.ohol_runtime/logs/last_run.json` (tail of actions, size-capped).

**Manual control (no autopilot):**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli control --frame-paced
# ohol> move 10 east
# ohol> move 6 south
# ohol> status
```

**Verify movement (no stuck-on-tree):**

```powershell
$env:PYTHONPATH='src'
python scripts/verify_bot_run.py 800
```

**Server won't start (`map.db` / KissDB error):** kill stale `OneLifeServer.exe`, delete `.ohol_runtime\server\map.db*` and `mapTime.db`, restart.

## Verify login only

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli login-probe
```

Expect `ACCEPTED`. For a short persistent session: `stay-alive --seconds 30 --watch`.
