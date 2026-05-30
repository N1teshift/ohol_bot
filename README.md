# OHOL Bot

Private-server research scaffold for building One Hour One Life bots.

**New session?** Start with [AGENTS.md](AGENTS.md) (quick onboarding) or the full
[Project Handoff](docs/PROJECT_HANDOFF.md) (goals, architecture, protocol, status,
next steps).

The first milestone is a reproducible private server plus a **live** Python bot that
stays connected, reads packets, and runs simple survival behaviors. Learning and
multi-agent cooperation sit on top of that platform.

## Quick start (live bot)

**Terminal 1 — server:**

```powershell
.\scripts\setup_private_server.ps1   # once
.\scripts\run_private_server.ps1
```

**Terminal 2 — autopilot bot:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --watch
```

Use `--frame-paced` for one planner step per server `FM` frame (recommended). Use `--tick-seconds N` for slower wall-clock pacing. Use `--forever` for an indefinite session (Ctrl+C to stop). Use `--max-ticks N` for a timed run.

Credentials default to `bot_001@local` / key `aaaa` on `localhost:8005` (see
[AGENTS.md](AGENTS.md)).

## Manual control

Drive the bot yourself from the terminal (no survival planner):

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli control --frame-paced
```

```
ohol> move 10 east
ohol> move 6 south
ohol> goto 5 12
ohol> status
ohol> help
ohol> quit
```

One-shot: `python -m ohol_bot.cli control move 10 east`. Add `--watch` for the dashboard after each command.

## What works today

- HMAC login and **persistent session** (read loop + `KA 0 0#` keep-alive)
- **LiveSessionEngine orchestration** for `run-live` loop pacing and stop reasons (while preserving CLI behavior)
- **World state** from PU, PM, FX, MC, MX (position, hunger, map objects, players)
- **World/action state split started**: `WorldState` (packet-derived) + `ActionFeedbackState` (move/eat/force feedback)
- **Survival planner** live: move to food, pick up, **eat held food (`SELF`)** — verified end-to-end on private server
- **Typed planner-facts adapter** (`planner_facts.py`) used by skills for avoid/blocked/remembered targets
- **Behavior-layer scaffold** (`behaviors.py`): `SurvivalBehavior` active, `RecipeBehavior` skeleton for next feature
- **RecipeBehavior v1 (opt-in)**: gathers early recipe resources; supports transition-driven goal inputs
- **Obstacle-aware pathfinding** (`movement.py`): 8-way BFS around `blocksWalking`, birth-relative coords, corner-cutting, approach tiles for blocked food
- **Wide collision v1**: uses `leftBlockingRadius`/`rightBlockingRadius` footprints when checking walkability
- **Stuck avoidance:** `avoid_targets` / `blocked_tiles`, rotating explore, adjacent pickup even when a food tile was avoided for walking
- **Hunger trigger**: forage when one stomach pip is missing (`food_store < max_food_store`)
- **`--frame-paced` loop**: one planner step per server **`FM`** frame; recommended for live play
- **Movement pacing**: one tile per `MOVE`; planner waits while `is_stationary=false`; MOVE blocked while in-flight or awaiting FORCE ack
- **Self player detection**: locked from first solo PU or first PM after our MOVE — **not** from LN
- **Action coordinates**: `_action_tile` + `birth_tile` offset for map (absolute) vs MOVE (relative) coords
- **Held-item tracking**: pending pickup after `USE`, latched hold, `held_yum` from PU; drop non-food when hungry
- **Terminal dashboard** (`--watch`)
- **Manual control** (`control` CLI)
- **`scripts/verify_bot_run.py`**: automated stuck detection after movement changes
- Game data loader (~4400 objects, transitions) from `.ohol_runtime/server`
- Mock scenarios and unit tests under `tests/`
- Full regression suite currently passing: `111` tests
- Full regression suite currently passing: `123` tests

## Bot API

`BotClient` (`src/ohol_bot/client.py`):

- `observe()` → `Observation`
- `move_to(tile)`, `pick_up(tile)`, `use(held_item, target)`, `use_self(tile)`, `drop(tile)`, `say(text)`, `wait(ticks)`

Live implementation: `OholProtocolClient` in `protocol_client.py`.

## CLI commands

Set `$env:PYTHONPATH='src'` first.

| Command | Purpose |
|---------|---------|
| `run-live` | Closed loop: observe → `SurvivalPlanner` → act (use `--watch`) |
| `control` | Interactive manual control — `move 10 east`, `goto x y`, `pick`, `eat`, … |
| `stay-alive` | Stay connected; optional `--say`, `--move-x/y`, `--watch` |
| `verify-live` | Automated say / move / eat checks against server |
| `login-probe` | Connect, login, read briefly |
| `action-probe` | Send one action (experimental) |
| `run-scenario` | Mock survival demo from JSON scenario |
| `parse-server-log` | Parse server terminal log |

Examples:

```powershell
python -m ohol_bot.cli run-live --forever --frame-paced --watch
python -m ohol_bot.cli run-live --enable-recipe-behavior --recipe-goal-object-id 99 --frame-paced --watch
python -m ohol_bot.cli control --frame-paced --watch
python -m ohol_bot.cli control move 10 east
python -m ohol_bot.cli stay-alive --seconds 60 --watch
python -m ohol_bot.cli verify-live
python scripts/verify_bot_run.py 800
python -m ohol_bot.cli run-scenario scenarios\find_food.json
```

## Private server sandbox

Your Steam install contains `OneLifeServer.exe`, `runServer.bat`, and settings.
Do not experiment inside `Program Files`; use the sandbox copy:

```powershell
.\scripts\setup_private_server.ps1
.\scripts\run_private_server.ps1
```

Runtime: `.ohol_runtime\server` (gitignored). Only one `OneLifeServer.exe` at a time. If startup fails on corrupt `map.db`, kill all server processes and delete `map.db*` / `mapTime.db` in that folder (fresh world map).

## Local GUI bot placeholder

```powershell
.\scripts\create_local_client.ps1 -ClientId bot_001
.\scripts\run_local_client.ps1 -ClientId bot_001
```

Separate credentials per bot copy avoid Steam single-session disconnects.

## Roadmap

| Area | Status |
|------|--------|
| Private server sandbox | Done |
| Protocol login + persistent client | Done |
| Live world state + planner loop | Done |
| Basic survival (food, home, branches) | Done |
| Live forage → pick up → eat (`USE_SELF`) | **Verified** |
| `--frame-paced` + movement gating | **Verified** |
| Obstacle-aware pathfinding (basic BFS) | **Done** (no wide collision yet) |
| Stuck-on-tree avoidance + verify script | **Done** |
| Manual terminal control | **Done** |
| Self-id + action-tile + birth-tile coords | Done |
| Held-by / eat-held-food behavior | Done |
| Session engine extraction | Done |
| World/action feedback split foundation | Done |
| Typed planner-facts adapter | Done |
| Behavior-layer scaffold | Done |
| RecipeBehavior v1 (opt-in gather) | Done |
| Transition-driven recipe input selection | Done |
| Wide collision footprint checks | Done (v1 approximation) |
| Recipe / transition planner (fire, tools) | Not started |
| Multi-bot family coordinator | Skeleton only |
| Wide collision / leftBlockingRadius | Not started |

See [docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md) for protocol details and next steps.
