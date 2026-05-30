# OHOL Bot — Project Handoff

This document captures project goals, architecture, what works, what does not, and recommended next steps. It is written for a fresh developer or AI coding agent starting with no prior conversation context.

**Related docs:** [README.md](../README.md), [reuse_decision.md](reuse_decision.md)

**Past conversation transcripts (if you need exact wording or history):**  
`C:\Users\user\.cursor\projects\c-Users-user-source-repos-ohol-bot\agent-transcripts\` (search by topic: protocol, run-live, held-by, eat)

---

## 1. Goal

Build bots for **One Hour One Life (OHOL)** that can play on a **private server**, survive, cooperate, and eventually help **sustain a family/lineage** when real players are scarce.

Long-term vision (not all implemented):

- Multi-bot cooperation and role assignment
- Scripted survival behaviors (food, tools, fire)
- Curriculum learning and scenarios
- Possibly reinforcement learning later

**Current engineering path:**

```
private server → persistent Python client → live world state → survival planner → (next) recipes / family
```

**Milestone reached:** single bot **forages, picks up food, and eats** on the private server (`USE` → `SELF`). **Basic obstacle-aware pathfinding** routes around trees; **manual terminal control** lets you walk N tiles in a direction.

**Architecture upgrade completed (safe incremental refactor):**

- `run_live_episode` now delegates to `LiveSessionEngine` (`runner.py`) for loop orchestration.
- `WorldState` now composes `ActionFeedbackState` (`world_feedback.py`) for move/eat/force feedback bookkeeping.
- Planner/skills now have a typed facts adapter (`planner_facts.py`) for avoid/blocked/remembered target inputs.
- Behavior scaffold added (`behaviors.py`) with `SurvivalBehavior` active and `RecipeBehavior` as an off-by-default skeleton.

Remaining work is still crafting/recipes, wide collision, and multi-bot coordination.

**Explicit scope choice:** one live bot first; multi-bot and recipe chains are deferred.

The user develops this project in parallel across multiple chat sessions. Treat this document as the source of truth for context handoff.

---

## 2. Environment

| Item | Value |
|------|-------|
| Workspace | `c:\Users\user\source\repos\ohol_bot` |
| Steam OHOL install | `C:\Program Files (x86)\Steam\steamapps\common\One Hour One Life` |
| Sandbox server runtime | `.ohol_runtime\server` (gitignored) |
| Sandbox bot client | `.ohol_runtime\clients\bot_001` (gitignored) |
| Python package | `src\ohol_bot\` — set `$env:PYTHONPATH='src'` before CLI use |
| Server address | `localhost:8005` |
| Tests | `tests\test_*.py` — `pytest` may not be installed; run via `python -c` or install pytest |

**Important:** Do not edit files directly under `Program Files`. Always use the sandbox copy via scripts.

**User preferences:**

- Do **not** edit `.cursor/plans/*.plan.md` unless the user asks
- Do **not** git commit unless the user asks
- Prefer sandbox paths over Steam install paths
- Reference [plannerbot](https://github.com/marius851000/plannerbot) and [oholbotframework](https://github.com/webmsgr/oholbotframework) conceptually; do not copy plannerbot code without checking license (see [reuse_decision.md](reuse_decision.md))

---

## 3. Architecture

```
SurvivalPlanner -> Behavior layer (planner.py, behaviors.py)
        ↓
SkillLibrary + typed planner facts adapter (skills.py, planner_facts.py)
        ↓
movement.py — BFS pathfinding, approach tiles, corner-cutting (blocksWalking)
        ↓
LiveSessionEngine (runner.py) — frame/tick pacing, observe/decide/act loop, stop reasons
        ↓
OholProtocolClient (protocol_client.py) — socket, login, read loop, keep-alive, action send
        ↓
WorldState + ActionFeedbackState (world_state.py, world_feedback.py)
  - packet-derived model from PU/PM/FX/MC/MX
  - action feedback (blocked/avoid, move in-flight, eat pending, FORCE recovery)
        ↓
protocol_messages.py + protocol_framing.py — parse SN, ACCEPTED, PU, PM, CM, MC, FX, LN, …
        ↓
game_data.py — object names, foodValue, transitions from sandbox
        ↓
Private OHOL Server (OneLifeServer.exe on localhost:8005)
```

**Current state:** A **single bot** can stay connected, build observations from streamed packets, and run a **closed-loop** `run-live` command with optional terminal **dashboard** (`--watch`). The refactor preserves behavior while creating clear seams for recipe and multi-bot work.

---

## 4. Repository Layout

```
ohol_bot/
├── config/
│   ├── private_server.json      # Server sandbox config + settings to apply
│   └── local_clients.json       # Bot client credentials (bot_001@local, etc.)
├── scripts/
│   ├── setup_private_server.ps1 # Copy Steam install → .ohol_runtime/server
│   ├── run_private_server.ps1   # Start OneLifeServer.exe
│   ├── create_local_client.ps1  # Copy client folder for bot_001
│   ├── run_local_client.ps1     # Launch GUI bot client
│   └── verify_two_players.ps1   # Check server log for 2 unique logins
├── src/ohol_bot/
│   ├── client.py                # BotClient ABC + MockBotClient
│   ├── model.py                 # Tile, Action, Observation, PlayerState
│   ├── protocol_client.py       # OholProtocolClient — live session + actions
│   ├── protocol_messages.py     # Message parser
│   ├── protocol_framing.py      # Binary MC/CM chunk framing
│   ├── world_state.py           # Packet-derived world model + observation builder
│   ├── world_feedback.py        # Action feedback state (blocked/avoid/eat pending/force)
│   ├── spatial_memory.py        # Working (radius 24) + long-term map memory (absolute tiles)
│   ├── resource_memory.py       # Branch/tree landmark names + collect matching helpers
│   ├── movement.py              # BFS pathfinding around blocksWalking
│   ├── game_data.py             # objects/ transitions from sandbox
│   ├── planner.py               # SurvivalPlanner orchestrating behavior modules
│   ├── behaviors.py             # Behavior layer (SurvivalBehavior + RecipeBehavior scaffold)
│   ├── skills.py                # Skill library consumed by behaviors
│   ├── planner_facts.py         # Typed adapter over observation.facts for planner/skills
│   ├── manual_control.py        # Interactive terminal control (control CLI)
│   ├── dashboard.py             # Terminal dashboard for --watch
│   ├── runner.py                # run_episode, run_live_episode
│   ├── live_behaviors.py        # verify-live harness
│   ├── family.py                # Multi-bot coordinator (skeleton)
│   ├── training.py, scenario.py, server_log.py
│   └── cli.py                   # CLI entry points
├── scripts/
│   └── verify_bot_run.py        # Live stuck-detection smoke test
├── scenarios/
│   ├── find_food.json
│   └── curriculum.json
├── tests/
└── docs/
    ├── PROJECT_HANDOFF.md       # This file
    └── reuse_decision.md
```

---

## 5. Private Server Sandbox

### Setup (once, or after `-Reset`)

```powershell
cd c:\Users\user\source\repos\ohol_bot
.\scripts\setup_private_server.ps1
```

Copies the Steam install to `.ohol_runtime\server` and writes settings from `config/private_server.json`:

| Setting | Value | Purpose |
|---------|-------|---------|
| `requireTicketServerCheck.ini` | `0` | Skip ticket server on private server |
| `secondsPerYear.ini` | `15.0` | Faster aging for tests |
| `forceEveAge.ini` | `18` | Spawn as adult Eve |
| `allowVOGMode.ini` | `1` | Allow VOG (spawn anywhere) |
| `vogAllowAccounts.ini` | `*` | All accounts can VOG |
| Client `vogModeOn.ini` | `1` | Client uses VOG mode |

Server password in sandbox: **`testPassword`**.

### Run server

```powershell
.\scripts\run_private_server.ps1
```

Keep this terminal open. Stop with **Ctrl+C**. Use `taskkill /IM OneLifeServer.exe /T /F` only if stuck.

**Known issue:** Only one `OneLifeServer.exe` at a time. Two instances cause `map.db` / KissDB lock errors.

---

## 6. Bot Clients

### GUI placeholder client (bot_001)

```powershell
.\scripts\create_local_client.ps1 -ClientId bot_001
.\scripts\run_local_client.ps1 -ClientId bot_001
```

### Working credentials (programmatic + GUI)

| Field | Value |
|-------|-------|
| email | `bot_001@local` |
| account_key | `aaaa` |
| client_id | `client_mariusbottest` |
| server_password | `testPassword` |
| custom server | `localhost:8005` |

**Why separate credentials:** Using the same Steam account in two normal clients disconnects the first. Separate copied clients with fake local credentials are the intended approach for dummy bot bodies.

---

## 7. Python CLI

Set Python path first:

```powershell
$env:PYTHONPATH='src'
```

| Command | Purpose |
|---------|---------|
| `run-live` | **Main loop:** login, read packets, planner tick, send actions. `--watch` shows dashboard. `--forever` runs until Ctrl+C. |
| `control` | **Manual control:** interactive REPL — `move 10 east`, `go south 6`, `goto x y`, `pick`, `eat`, `status`. No autopilot planner. |
| `stay-alive` | Stay connected; optional `--say`, `--move-x/y`, `--watch` |
| `verify-live` | Automated say / move / eat checks |
| `login-probe` | Connect + HMAC login + read briefly (disconnects after probe) |
| `action-probe` | Send one action type (experimental; may not login first) |
| `run-scenario` | Mock survival demo from `scenarios/*.json` |
| `parse-server-log` | Parse server terminal log |

**Script (not CLI subcommand):** `python scripts/verify_bot_run.py [max_ticks]` — runs the live bot and **fails if stuck** (same tile too long, spamming one move target, too many invalid paths). Run after movement/pathfinding changes. Server must be up.

### Recommended live session

**Terminal 1:** `.\scripts\run_private_server.ps1`

**Terminal 2:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --watch
```

Notes:

- **`--forever`**: runs until Ctrl+C or starvation; ignores `--max-ticks`.
- **`--max-ticks N`**: ends the session after N planner ticks via graceful `close()` — not a server crash.
- **`--frame-paced`**: one planner step per server **`FM`** frame (recommended for speed; ignores `--tick-seconds`).
- **`--tick-seconds`**: wall-clock polling interval when not using `--frame-paced` (default `1.0`; each action also waits again after send).
- **`--watch`**: terminal dashboard (position, hunger, held item, planner reason).
- **`--game-data-root`**: defaults to `.ohol_runtime/server` for object names, `foodValue`, and `blocksWalking` pathfinding.

### Manual control session

**Terminal 1:** `.\scripts\run_private_server.ps1`

**Terminal 2:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli control --frame-paced
```

At the `ohol>` prompt:

```
move 10 east          # walk 10 tiles east, one step at a time
go south 6            # same as move 6 south
goto 12 -4            # pathfind toward tile (12, -4)
status                # tile, hunger, held item
pick 5 3              # USE on ground tile
eat                   # SELF (eat held food)
help / quit
```

Directions: `north`/`south`/`east`/`west` (or `n`/`s`/`e`/`w`), `up`/`down`, diagonals `ne`/`nw`/`se`/`sw`. One-shot: `python -m ohol_bot.cli control move 10 east`.

---

## 8. OHOL Protocol (Critical)

Correct flow (from official client source + plannerbot reference):

### Login handshake

1. Connect TCP to server (`localhost:8005`)
2. Read **`SN`** challenge (frames end with `#`)
3. Send **`LOGIN`** with **HMAC-SHA1**:

```
LOGIN <client_id> <email padded to 80 chars> <hmac(server_password, challenge)> <hmac(pure_account_key, challenge)> <tutorial_flag>#
```

- `pure_account_key` = account key with hyphens removed
- Sandbox server password: `"testPassword"`

4. Receive **`ACCEPTED`** or **`REJECTED`**

Implementation: `build_login_message()` in `protocol_client.py`.

### Message framing

- Messages terminate with **`#`**
- Multiple messages can arrive in one `recv()` — split on `#`
- Map chunks (**MC** / **CM**) use binary framing helpers in `protocol_framing.py`

### Action message shapes

| Intent | Message format |
|--------|----------------|
| Say | `SAY 0 0 text#` |
| Move | `MOVE start_x start_y @seq dx dy#` — bot sends **one tile per step**; `_resolve_move_step()` uses BFS pathfinding when game data is loaded |
| Force | `FORCE x y#` |
| Use / pick up (ground) | `USE target_x target_y#` |
| Eat held food | `SELF x y -1#` (`ActionType.USE_SELF`) |
| Drop | `DROP x y slot#` (slot often `-1`) |
| Keep-alive | `KA 0 0#` |

Implementation: `serialize_action()` in `protocol_client.py`.

**Eating nuance:** `USE` on ground food often **picks it up**. Eating requires **`SELF`** on your tile while holding food with `foodValue > 0`. The forage skill picks up first, then sends `USE_SELF` on the next tick.

### Parsed message families

`protocol_messages.py` handles: **SN**, **ACCEPTED**, **REJECTED**, **FM**, **PU**, **PM**, **PS**, **CM** (zlib), **MC**, **MX**, **FX**, **LN**.

`WorldState.apply()` updates players, hunger (**FX**), and map objects (**MC** / **MX**).

**Self player id:** locked in `OholProtocolClient` from the **first solo PU** after login, or the **first PM** after the bot sends a MOVE. Do **not** use **LN** (lineage) — each LN line describes a different player’s ancestry; the last line is often a nearby player, not self. Wrong self id breaks hunger, held state, and dashboard player id.

**Action tile (`_action_tile`):** coordinates sent in MOVE/SELF must match the server’s idea of where the player is. Updated on confirmed PU/PM — not optimistically advanced on MOVE send.

**Birth-relative coordinates:** map objects from MC/MX use **absolute** world coords; MOVE/PU use coords **relative to spawn**. `WorldState.birth_tile` converts between them so pathfinding and nearby-object distance checks stay correct when spawning far from origin.

**Move sequence:** PU field 12 is `done_moving_seq` (sequence number, not a boolean). `WorldState.move_in_flight()` blocks new MOVEs until the server confirms the step. After server **FORCE** (invalid path), bot waits for next **FM** before sending again (`_awaiting_force_ack`).

**Server time steps (`FM`):** each server tick ends with an **`FM`** frame. With **`--frame-paced`**, the bot waits for `FM`, then decides once. High `protocol msgs` / `server frames` counts on the dashboard are normal in this mode.

**Movement gating:** the official client sends one action at a time and waits until movement finishes. The bot mirrors this: `action_blocker()` returns non-`None` while `is_stationary=false`; planner returns `WAIT`; `OholProtocolClient.send()` drops non-wait actions while moving, while a move is in-flight, or while awaiting FORCE ack.

### Player update (PU) fields used

| Field index | Meaning |
|-------------|---------|
| 6 | Holding (`o_id`): positive = object id (container format: `id,contained,...`); **negative = baby player id** |
| 12 | `done_moving_seq` — move-finish sequence (> 0 when step completed); also signals baby dropped when carried |
| 14, 15 | Position `xd`, `yd` |
| 16 | Age (years at last PU) |
| 17 | `invAgeRate` — seconds per in-game year (sandbox: 15.0); used to **interpolate live age** between PUs |
| 20 | `just_ate` — player ate what they were holding |
| 24 | `held_yum` — `1` if held item is yummy food |
| 25 | `held_learned` — tool learning flag (parsed, not yet used by planner) |

**Carried state:** when adult PU has holding `-babyId`, `WorldState` sets baby's `held_by_player_id` to that adult. Planner returns **WAIT** while `is_being_carried`.

**Held-item nuance:** During movement the server may send PU lines with `o_id=0` even though the client still shows an item in hand. The bot **latches** a confirmed held object id and ignores stale empty-hand PUs unless `just_ate` or the bot sent `USE_SELF` / `DROP`. Local **pending pickup** tracks the object id after `PICK_UP` until PU confirms.

**Stationary nuance:** PU field 12 (`done_moving_seq`) is a **move-finish sequence number** (> 0 when a step completed). Only matching finish PUs clear in-flight state and mark stationary. PM and outgoing MOVE set moving; a 30s timeout clears stale motion if no finish PU arrives. Stuck detection: 4 ticks unchanged while targeting the same tile adds it to `avoid_targets`.

**Age nuance:** Dashboard **planner tick** is the `run-live` loop counter; **protocol msgs** is `WorldState.tick` (one per parsed packet). Age on the dashboard is a **live estimate** (`age + elapsed / invAgeRate`), not the planner tick. Babies cannot self-act below `NO_MOVE_AGE = 0.20` years (~3s at 15s/year).

---

## 9. Survival Planner (Current Behavior)

`SurvivalPlanner.decide()` priority:

1. **Being carried** → `WAIT` (no movement or actions)
2. **Still moving** (`not is_stationary`) → `WAIT` until current step finishes (`hunger.action_blocker`)
3. **Hungry** (`is_planner_hungry` — at least **one stomach pip missing**):
   - Holding food → `USE_SELF` (eat) unless blocked (`hunger.eat_blocker`: too young, not stationary, eat pending)
   - Holding non-food → `DROP` to free hands
   - Adjacent food (8-way) → `PICK_UP` even if that tile is in `avoid_targets` (failed walk path)
   - Else nearest food → `MOVE_TO` (pathfinder sends one tile per frame toward target or approach tile)
   - No visible food → **explore**: one step in a rotating direction, skipping `blocked_tiles`, `avoid_targets`, and `previous_tile` (anti ping-pong)
4. **Far from home** (> 12 tiles) → `MOVE_TO` home (one tile per step)
5. **Empty hands** → collect nearest `straight branch` / `curved branch`
6. Else → `WAIT`

Skills live in `skills.py`. `WorldState.to_observation()` enriches held items via `game_data.py` (name, `foodValue`), merges pending/latched state, and exposes `avoid_targets`, `blocked_tiles`, `previous_tile`, and `birth_tile` in `observation.facts`.

### Spatial memory (working + long-term)

`spatial_memory.py` sits on top of raw `tile_objects` (absolute coords from MC/MX). **`tile_objects` is unchanged** — pathfinding still uses the full ingest cache.

| Store | Rule | Coordinates |
|-------|------|-------------|
| **Working** | Objects within Manhattan distance ≤ 24 of bot absolute position | Absolute keys; `nearby_objects` uses relative tiles for actions |
| **Long-term** | Tiles that leave working view (bot moved away) | Absolute; `last_seen_tick` updated on promotion |

Sync runs each `to_observation()`. MX/MC clears and optimistic `PICK_UP`/`USE` call `forget_tile`. Long-term is capped at **500** entries and evicts entries older than **3000** ticks.

`observation.facts` includes `working_memory_count`, `long_term_memory_count`, `long_term_food_count`, `nearest_remembered_food`, `nearest_remembered_collect` (with `rel_x`/`rel_y` for navigation), previews, and `long_term_by_biome` counts.

**Landmark resource memory (v1):** long-term entries store `biome_id` at sighting. [`resource_memory.py`](../src/ohol_bot/resource_memory.py) defines branch names and tree-like names (`* Tree`). Planner [`forage_food`](../src/ohol_bot/skills.py) walks toward `nearest_remembered_food` before explore; [`collect_named_object`](../src/ohol_bot/skills.py) walks toward `nearest_remembered_collect` (branches + trees) when nothing is in working range. Priority eviction keeps food/branch/tree landmarks longer under the 500 cap.

**Phase 2:** resource **sites** (tile clusters), biome **attractors** for unseen exploration, fixed regions with object histograms.

### Terminal dashboard (`--watch`)

Single **Self** panel (no separate “inventory” view). Key lines:

| Line | Meaning |
|------|---------|
| `planner tick N` / `protocol msgs M` / `server frames F` | Loop count vs parsed packets vs `FM` frames (frame-paced only) |
| `Age: … (live estimate)` | Interpolated age; `Age at last PU` is raw server snapshot |
| `Stationary` / `Forage blocked by` | Must be stationary to eat; while moving, planner waits |
| `Held: …` | Object name and id; may show `pending server confirm` after pickup |
| `Held food: yes/no` | Whether planner will try `USE_SELF` |
| `Carried by: …` | Adult player id if being carried, else `nobody` |
| `Planner / Reason` | Last action and human-readable explanation |

If `Held` flips from pie → `nothing` while the in-game sprite still holds food, that was a **stale PU with `o_id=0`** — fixed by held-item latching (see section 12).

---

## 10. What Works (Verified)

- Private server starts on `localhost:8005`
- Python **HMAC login** → `ACCEPTED`; server log: `New player bot_001@local connected`
- **Persistent session:** read loop, periodic `KA`, graceful shutdown
- **Live bot visible** in world during `stay-alive` / `run-live`
- **World state:** player position (PU/PM), hunger (FX), map tiles (MC/MX), ~100+ tracked objects at spawn
- **Planner loop:** `run-live` with dashboard; forage / explore / return home / collect branches
- **Frame-paced loop (`--frame-paced`):** `wait_for_frame()` → decide → act once per server step; no double wall-clock sleep
- **Movement gating + one-tile MOVE:** verified live; pathfinding routes around `blocksWalking` trees
- **Stuck-on-tree fixes:** avoid/blocked tiles, rotating explore, adjacent pickup, FORCE ack gating, birth-tile coords
- **`scripts/verify_bot_run.py`:** automated stuck detection (unchanged tile, spam target, invalid paths)
- **Manual control (`control` CLI):** walk N tiles in a direction from terminal REPL
- **Eat held food (verified live):** move → `USE` pick up → `SELF x y -1#` at **`_action_tile`** → FX food increase / `just_ate` PU
- **Self player id lock:** first solo PU or PM-after-MOVE; LN no longer overwrites id
- **Action tile sync:** MOVE/SELF use `_action_tile` so server accepts actions after multi-step moves
- **Stationary for eat:** pickup PUs no longer falsely mark “still moving”
- **Live age estimate:** field 16 + 17 interpolation; dashboard shows estimate vs last PU
- **Held-item latch:** stale PU with empty `o_id` no longer clears a confirmed hold mid-move
- **Pending pickup:** dashboard shows held item immediately after `PICK_UP` before PU confirms
- **Carried awareness:** negative holding on adult PU → baby waits
- **`run-live --forever`:** indefinite session until Ctrl+C or starvation
- **Early hunger:** forage when one food pip is missing (good for testing eat behavior)
- **verify-live** harness for say, move, eat behaviors
- Game data: ~4400 objects, transitions from sandbox
- Mock scenarios + unit tests (`tests/test_survival.py`, `test_protocol_client.py`, etc.)

---

## 11. What Does NOT Work Yet / Limitations

| Gap | Notes |
|-----|-------|
| Recipe / craft planner | No transition chains (sharp stone, fire, etc.) |
| Wide collision | `leftBlockingRadius` not modeled — trees may block adjacent tiles server-side |
| Pathfinding polish | BFS + `blocksWalking` done; no deadly tiles, distance limits, or batched multi-step MOVE |
| Mother-specific carry | Waits when **any** adult carries the bot, not only `mother_id` |
| `action-probe` | Does not always login before sending actions |
| Multi-bot live | `family.py` is skeleton only; user deferred second bot |
| Full map memory | `tile_objects` cache grows with server sends; working/long-term split is explicit but planner still uses `nearby_objects` only |
| Biome attractors / fixed regions | Landmarks only; `tile_biomes` is flat coords, no regional clustering yet |
| pytest in CI | May need `pip install pytest` locally |
| All food edge cases | Gooseberry/berry path verified; sparse biomes may starve during long explore |
| LN for lineage graph | LN parsed but not used for self id or `mother_id` yet |

---

## 12. Errors Encountered and Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Second client disconnects first | Same Steam account | Separate local credentials in `bot_001` copy |
| `map.db` / KissDB error on server start | Unclean shutdown or stale process | `taskkill /IM OneLifeServer.exe /T /F`; delete `.ohol_runtime\server\map.db*` and `mapTime.db`; restart |
| Login `REJECTED` | Plain SHA1 or wrong password | HMAC with SN challenge; `aaaa` + `testPassword` |
| Bot picks up food but does not eat | `USE` picks up; eat needs `SELF` | `USE_SELF` when `is_holding_food` |
| Dashboard shows `Held: nothing` while holding pie in-game | Stale PU with `o_id=0` overwrote state | Latch confirmed hold; pending pickup; parse `held_yum` (field 24) |
| Held showed pie on tick 5, `nothing` on tick 6 | Mid-move PU said empty hands | Same latch fix — do not trust single empty PU |
| `run-live` disconnects after N ticks | `--max-ticks` intentional | Use `--forever` or increase `--max-ticks` |
| Probe "Socket read failed" | Short `login-probe` session | Use `stay-alive` or `run-live` for sustained play |
| Age stuck at 0.0 on dashboard | Age only on PU; planner tick ≠ game age | Interpolate with field 17; label ticks clearly |
| Bot waits forever while holding food | Pickup PU set `is_stationary=false` | Only `done_moving > 0` sets stationary true |
| `SELF` sent but no eat in game | Wrong tile (PU lag after MOVE) or wrong self id | `_action_tile`; lock self id, ignore LN for self |
| Dashboard player id ≠ server log id | LN last line used as self | Lock self from first solo PU / PM after MOVE |
| Bot stuck mid-move (frame-paced) | New `MOVE` every `FM` while still walking | `action_blocker` + wait until stationary; one tile per `MOVE` |
| Bot stuck on tree / ping-pong | Explore always north; food in `avoid_targets` blocked pickup | Rotating explore, skip previous tile, adjacent pickup, pathfinding + avoid list |
| Invalid path + MOVE spam | FORCE + MOVE same tick; wrong coords | Await FORCE ack on FM; birth-relative coords; corner-cutting |
| Default `--tick-seconds 1` feels slow | Double `poll_until` (~2s per action) | Use `--frame-paced` for server-step speed |

---

## 13. Roadmap Status

| Phase | Status |
|-------|--------|
| Private server sandbox | Done |
| Bot interface abstraction | Done |
| Observation/action data model | Done |
| Protocol login + HMAC | Done |
| **Persistent live client** | **Done** |
| **World state from packets** | **Done** |
| **Live survival planner loop** | **Done** |
| Held-by awareness + eat held food | Done |
| **Live eat verified (forage → SELF)** | **Done** |
| Self-id lock + action tile sync | Done |
| Stationary + live age on dashboard | Done |
| Held-item latch + pending pickup | Done |
| Early hunger (one pip missing) | Done |
| `run-live --forever` | Done |
| **`--frame-paced` loop** | **Done** |
| Movement gating + one-tile steps | Done |
| Obstacle-aware pathfinding (basic BFS) | Done |
| Stuck avoidance + verify_bot_run.py | Done |
| Manual terminal control | Done |
| Terminal dashboard | Done |
| Scripted survival (mock scenarios) | Done |
| Game data parser | Done |
| Curriculum scenarios | Scaffold |
| Multi-agent family coordinator | Skeleton only |
| **Recipe / transition planner** | **Not started — next feature** |
| Wide collision / pathfinding polish | Partial (BFS + blocksWalking only) |
| Second live bot + coordination | Deferred |

---

## 14. Recommended Next Steps (Priority Order)

### 1. Recipe / transition planner

Use `game_data.py` transitions for early chains: sharp stone, fire, basic tools. Small planner module that emits sequences of `USE` / `PICK_UP` / `DROP` before folding into `SurvivalPlanner`.

### 2. Pathfinding polish

Wide collision (`leftBlockingRadius`), batched multi-step MOVE (plannerbot sends up to 10), deadly tiles. Reference plannerbot for ideas; see [reuse_decision.md](reuse_decision.md).

### 3. Richer carry / family logic

Parse **LN** for `mother_id` / lineage graph (do **not** use LN for self player id). Only wait when carried by mother (optional). Feed baby detection via **FX** / responsible player fields if needed.

### 4. Second bot (when user wants)

`bot_002@local`, separate `stay-alive` / `run-live`, wire `family.py` roles over shared state or server log.

### 5. Hardening

- `action-probe` should login before actions
- `requirements.txt` + pytest in dev instructions
- Broader live tests (craft, die, respawn)
- Run `python scripts/verify_bot_run.py 800` after movement changes

---

## 15. Reference Repositories

| Repo | Use |
|------|-----|
| [marius851000/plannerbot](https://github.com/marius851000/plannerbot) | Rust client — login, movement, pathfinding, game data. No clear license; reference only. |
| [webmsgr/oholbotframework](https://github.com/webmsgr/oholbotframework) | Python MITM parser (LGPL-2.1). Optional integration later. |

Decision: stay native Python. See [reuse_decision.md](reuse_decision.md).

---

## 16. Key Code Entry Points

| Task | Start here |
|------|------------|
| Live session / keep-alive | `protocol_client.py`, `cli.py` (`run-live`, `stay-alive`) |
| Manual terminal control | `manual_control.py`, `cli.py` (`control`) |
| Pathfinding | `movement.py`, `protocol_client._resolve_move_step()` |
| Stuck detection smoke test | `scripts/verify_bot_run.py` |
| Frame-paced loop | `runner.py` (`frame_paced=True`), `protocol_client.wait_for_frame()` |
| Self id + action tile + birth tile | `protocol_client.py`, `world_state.py` (`birth_tile`, `to_absolute`) |
| World state / observations | `world_state.py`, `protocol_messages.py` |
| Survival logic | `planner.py`, `skills.py` |
| Eat / move blockers | `hunger.py` (`action_blocker`, `eat_blocker`), `serialize_action()` |
| Held-item state | `world_state.py` (`pending_held_object_id`, `latched_self_held_object_id`, `held_yum`) |
| Avoid / blocked tiles | `world_state.py` (`avoid_targets`, `blocked_tiles`), `skills._explore_step()` |
| Age + stationary | `world_state.py`, `hunger.py`, `dashboard.py` |
| Carried by adult | `world_state.py` (`held_baby_id`, `held_by_player_id`), `planner.py` |
| Dashboard | `dashboard.py` |
| Object/transition data | `game_data.py` |
| Mock testing | `client.py` (`MockBotClient`), `scenarios/`, `tests/` |
| Multi-bot roles (future) | `family.py` |

---

## 17. Quick Command Reference

```powershell
# Setup (once or after reset)
.\scripts\setup_private_server.ps1
.\scripts\create_local_client.ps1 -ClientId bot_001

# Terminal 1: server
.\scripts\run_private_server.ps1

# Terminal 2: live bot with dashboard
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --watch

# Manual control (no autopilot)
python -m ohol_bot.cli control --frame-paced

# Stuck-detection smoke test (server must be running)
python scripts/verify_bot_run.py 800

# Timed session (50 ticks)
python -m ohol_bot.cli run-live --max-ticks 50 --tick-seconds 1 --watch

# Short checks
python -m ohol_bot.cli login-probe
python -m ohol_bot.cli stay-alive --seconds 30 --watch
python -m ohol_bot.cli verify-live
python -m ohol_bot.cli run-scenario scenarios\find_food.json
```

---

*Last updated: May 2026 — obstacle-aware pathfinding, stuck avoidance, manual `control` CLI, `verify_bot_run.py`; birth-tile coords; FORCE ack gating.*
