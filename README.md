# OHOL Bot

Private-server research scaffold for building One Hour One Life bots.

**New session?** Start with [AGENTS.md](AGENTS.md) (quick onboarding) or the full
[Project Handoff](docs/PROJECT_HANDOFF.md) (goals, architecture, protocol, status,
next steps).

The current milestone is a reproducible private server plus a **live** Python bot
focused on movement: idle telemetry, chat-command follow mode, and smoother
server-confirmed walking. Survival and recipe behavior are parked as legacy
scaffolding while movement is rebuilt.

## Quick start (live bot)

**Terminal 1 — server:**

```powershell
.\scripts\setup_private_server.ps1   # once
.\scripts\run_private_server.ps1
```

**Terminal 2 — movement bot:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --watch
```

Say `follow` in game from the player you want the bot to follow. Say `stop follow`
to return the bot to idle.

While following, the bot waits on the same tile as the leader or any adjacent
tile (Chebyshev distance <= 1). It only moves when the leader is 2+ tiles away,
pathing toward a walkable tile exactly one step from the leader.

**Terminal 2 — unified follow + manual override mode:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli play
```

Shortcut (no env setup):

```powershell
.\scripts\run_bot_play.ps1
```

`play` enables frame-paced idle/follow mode with dashboard and accepts one-shot
manual `control` commands via `cmd>` (for example `move 5 east`, `goto 10 -3`,
`status`). Manual commands override one turn, then the movement policy resumes.

`play` session logs are written to `.ohol_runtime/logs/last_play.json` (includes manual command/plan events).

Use `--frame-paced` for one decision per server `FM` frame (recommended). Use
`--tick-seconds N` for slower wall-clock pacing. Use `--forever` for an
indefinite session (Ctrl+C to stop). Use `--max-ticks N` for a timed run.

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
- **Movement follow policy** live: idle by default, follow the player who says `follow`, return to idle on `stop follow`; wait at distance <= 1, move at distance >= 2
- **Structured chat parsing** for `PS` command events
- **Typed planner-facts adapter** (`planner_facts.py`) used by skills for avoid/blocked/remembered targets
- **Behavior-layer scaffold** (`behaviors.py`): `SurvivalBehavior` active, `RecipeBehavior` skeleton for next feature
- **Obstacle-aware pathfinding** (`movement.py`): 8-way BFS around `blocksWalking`, diagonal straight-line prefixes, birth-relative coords, corner-cutting, approach tiles for blocked food
- **Wide collision v1**: horizontal-only footprints from `leftBlockingRadius`/`rightBlockingRadius` when checking walkability
- **Stuck avoidance:** `blocked_tiles` hard-block walking; `avoid_targets` hard-skip explore/survival paths but are a soft penalty for follow formation targets
- **`--frame-paced` loop**: one movement decision per server **`FM`** frame; recommended for live play
- **Movement pacing**: one policy decision per stationary frame; each `MOVE` may encode a short batched path (cardinal + diagonal offsets, up to 6 steps) when the path is clear
- **Self player detection**: locked from first solo PU or first PM after our MOVE — **not** from LN
- **Action coordinates**: `_action_tile` + `birth_tile` offset for map (absolute) vs MOVE (relative) coords
- **Movement dashboard** (`--watch`): goal, last chat, action status, Chebyshev leader/player distance, follow target, blocked/avoid counts
- **Manual control** (`control` CLI)
- **`scripts/verify_bot_run.py`**: automated stuck detection after movement changes
- Game data loader (~4400 objects, transitions) from `.ohol_runtime/server`
- Mock scenarios and unit tests under `tests/`
- Full regression suite currently passing: `148` tests

## Bot API

`BotClient` (`src/ohol_bot/client.py`):

- `observe()` → `Observation`
- `move_to(tile)`, `pick_up(tile)`, `use(held_item, target)`, `use_self(tile)`, `drop(tile)`, `say(text)`, `wait(ticks)`

Live implementation: `OholProtocolClient` in `protocol_client.py`.

## CLI commands

Set `$env:PYTHONPATH='src'` first.

| Command | Purpose |
|---------|---------|
| `run-live` | Closed loop: observe → idle/follow movement policy → act (use `--watch`) |
| `play` | Unified live mode: idle/follow + one-shot manual overrides + dashboard |
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
python -m ohol_bot.cli play
python -m ohol_bot.cli control --frame-paced --watch
python -m ohol_bot.cli control move 10 east
python -m ohol_bot.cli stay-alive --seconds 60 --watch
python -m ohol_bot.cli verify-live
python scripts/verify_bot_run.py 800
python scripts/verify_follow_mode.py <leader_player_id> 800
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
| Obstacle-aware pathfinding (8-way BFS + diagonal prefixes) | Done |
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
| Wide collision footprint checks | Done (horizontal v1) |
| Recipe / transition planner (fire, tools) | Not started |
| Multi-bot family coordinator | Skeleton only |

See [docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md) for protocol details and next steps.
