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

**Milestone reached:** single bot can run a movement-first live loop, follow a leader via chat, and move smoothly through server-confirmed paths. Legacy survival behavior also **forages, picks up food, and eats** on the private server (`USE` → `SELF`). Obstacle-aware pathfinding routes around blockers, supports diagonal/dynamic batched paths, and manual terminal control lets you walk N tiles in a direction.

**Architecture upgrade completed (safe incremental refactor):**

- `run_live_episode` now delegates to `LiveSessionEngine` (`runner.py`) for loop orchestration.
- `WorldState` now composes `ActionFeedbackState` (`world_feedback.py`) for move/eat/force feedback bookkeeping.
- Planner/skills now have a typed facts adapter (`planner_facts.py`) for danger/blocked/remembered target inputs.
- Behavior scaffold added (`behaviors.py`) with `SurvivalBehavior` active and `RecipeBehavior` as an off-by-default skeleton.

**Post-refactor progress (implemented):**

- `run-live` and `play` now use the movement-first idle/follow policy by default.
- Incoming `PS` chat is parsed into command events; `follow` starts following the speaker, `collect <item>` / `collect stack <item>` gather objects, and `stop follow` / `stop collect` / `idle` return to idle.
- Recipe/survival behavior is parked as legacy scaffolding instead of driving the live runtime.
- Movement now sends dynamic batched MOVE paths (2 in follow or near danger/blockers; up to 10 in open `collect` / `collect_stack` paths), uses diagonal straight-line prefixes, considers horizontal object collision footprints, and hard-blocks danger tiles plus a 1-tile buffer in pathfinding.
- The dashboard includes a compact local tile map plus path diagnostics. `#` = blocked, `!` = dangerous animals. Follow target selection scores adjacent leader tiles by known reachability/path cost instead of geometry alone.

Remaining work is wider deadly buffers / remembered threats beyond working radius, smoother trail movement in very dense terrain, long-run hunger handling, crafting/recipes, and multi-bot coordination.

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
Decision layer:
  - MovementFollowPolicy (movement_policy.py) — idle/follow live default
  - SurvivalPlanner / Behavior layer (planner.py, behaviors.py) — legacy/scenario autonomy
        ↓
SkillLibrary + typed planner facts adapter (skills.py, planner_facts.py; survival path)
        ↓
movement.py — BFS pathfinding, dynamic batched paths, diagnostics, diagonal prefixes, approach tiles, corner-cutting (blocksWalking)
        ↓
LiveSessionEngine (runner.py) — frame/tick pacing, observe/decide/act loop, stop reasons
        ↓
OholProtocolClient (protocol_client.py) — socket, login, read loop, keep-alive, action send
        ↓
WorldState + ActionFeedbackState (world_state.py, world_feedback.py)
  - packet-derived model from PU/PM/FX/MC/MX
  - action feedback (blocked tiles, move in-flight, eat pending, FORCE recovery)
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
│   ├── world_feedback.py        # Action feedback state (blocked tiles, eat pending, force)
│   ├── danger.py                # Dangerous animal detection + path-safety helpers
│   ├── spatial_memory.py        # Working (radius 24) + long-term map memory (absolute tiles)
│   ├── resource_memory.py       # Branch/tree landmark names + collect matching helpers
│   ├── movement.py              # BFS pathfinding + dynamic diagonal paths + diagnostics + wide-collision footprint checks
│   ├── movement_policy.py       # MovementFollowPolicy orchestrator (idle/follow/collect/stack/camp)
│   ├── movement_chat.py         # Chat command parsing for movement modes
│   ├── movement_facts.py        # MovementFacts annotation on observation.facts
│   ├── follow_target.py         # Follow formation target scoring/selection
│   ├── stack_collect.py         # Stack/collect/camp runtime state and helpers
│   ├── harvest_flow.py          # Dig-harvest flow re-exports from stack_collect
│   ├── collect_rules.py         # Typed HarvestRule / StackCollectRule dataclasses
│   ├── interact_flow.py         # Orthogonal interact adjacency + navigate/pickup/drop helpers
│   ├── action_pending.py        # PendingAction retry/settle timers
│   ├── tiles.py                 # Chebyshev/adjacency, fact tile parsing, danger_tiles()
│   ├── spatial_queries.py       # nearest_object(), object_at_tile()
│   ├── object_names.py          # Item name normalization and stone/rock matchers
│   ├── map_debug.py             # Compact ASCII local tile map for movement debugging
│   ├── game_data.py             # objects/ transitions from sandbox
│   ├── planner.py               # SurvivalPlanner orchestrating behavior modules
│   ├── behaviors.py             # Behavior layer (SurvivalBehavior + RecipeBehavior scaffold)
│   ├── skills.py                # Skill library consumed by behaviors
│   ├── planner_facts.py         # Typed adapter over observation.facts for planner/skills
│   ├── recipe_graph.py          # Transition helpers for direct recipe producer lookup
│   ├── manual_control.py        # Interactive terminal control (control CLI)
│   ├── dashboard.py             # Terminal dashboard for --watch
│   ├── runner.py                # run_episode, run_live_episode
│   ├── live_behaviors.py        # verify-live harness
│   ├── family.py                # Multi-bot coordinator (skeleton)
│   ├── training.py, scenario.py, server_log.py
│   └── cli.py                   # CLI entry points
├── scripts/
│   ├── verify_bot_run.py        # Live stuck-detection smoke test
│   └── verify_follow_mode.py    # Live follow-distance smoke test
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
| `run-live` | **Movement loop:** login, read packets, idle/follow policy, send movement actions. `--watch` shows dashboard. `--forever` runs until Ctrl+C. |
| `play` | **Unified mode:** frame-paced idle/follow + dashboard + one-shot manual command overrides from `cmd>` prompt. |
| `control` | **Manual control:** interactive REPL — `move 10 east`, `go south 6`, `goto x y`, `pick`, `eat`, `status`. No autopilot planner. |
| `stay-alive` | Stay connected; optional `--say`, `--move-x/y`, `--watch` |
| `verify-live` | Automated say / move / eat checks |
| `login-probe` | Connect + HMAC login + read briefly (disconnects after probe) |
| `action-probe` | Send one action type (experimental; may not login first) |
| `run-scenario` | Mock survival demo from `scenarios/*.json` |
| `parse-server-log` | Parse server terminal log |

**Scripts (not CLI subcommands):** `python scripts/verify_bot_run.py` runs a **15-second** movement-only smoke policy and **fails if stuck** (same tile too long, spamming one move target, too many invalid paths). Use `--seconds N` and optional `--max-ticks N` for longer checks (e.g. `--seconds 60 --max-ticks 800`). Positional `verify_bot_run.py 800` still works but is deprecated. `python scripts/verify_follow_mode.py <leader_player_id> [max_ticks]` checks adjacent follow behavior against a known live leader. Server must be up.

### Recommended live session

**Terminal 1:** `.\scripts\run_private_server.ps1`

**Terminal 2:**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --planner-hz 6 --watch
```

### Unified interactive session (autopilot + manual overrides)

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli play
```

At `cmd>` you can use manual-control commands (`move`, `goto`, `pick`, `eat`, `status`, `help`, `quit`). In-game chat command `follow` from another player switches the bot into follow mode; `stop follow` / `idle` returns it to idle. Manual terminal commands override one step, then the movement policy resumes.

Notes:

- **`--forever`**: runs until Ctrl+C; ignores `--max-ticks`.
- **`--max-ticks N`**: ends the session after N movement ticks via graceful `close()` — not a server crash.
- **`--frame-paced`**: prefer server **`FM`**-aligned stepping; pairs well with **`--planner-hz`** (see below).
- **`--planner-hz N`**: fixed planner loop at **N Hz** (e.g. `6`). Each tick polls the socket and sends keep-alive at `1/N` seconds so the OHOL server keeps stepping when no other players are nearby. **Recommended for solo smoothness:** `--planner-hz 6` with `--frame-paced`. Without it, a lone bot may see ~1 server step/sec because the private server is **message-reactive** (more inbound traffic → more `FM` frames).
- **`--tick-seconds`**: wall-clock polling when neither `planner_hz` nor strict frame-wait is used (default `1.0`; non-`WAIT` actions also wait again after send).
- **`--watch`**: terminal dashboard (position, goal, last chat, action status, leader/follow/collect target, blocked/danger counts, danger nearby preview, path diagnostics, local tile map, **per-5s rate counters** on planner/world/server/KA).
- **`--game-data-root`**: defaults to `.ohol_runtime/server` for object names, `foodValue`, `blocksWalking`, and `deadlyDistance` pathfinding/danger checks.

### Movement follow policy (live default)

`MovementFollowPolicy` (`movement_policy.py`) drives `run-live` and `play`.

- **Idle:** `WAIT` unless a chat command changes mode.
- **Follow trigger:** another player's `PS` chat `follow` (case-insensitive); `stop follow`, `stop following`, or `idle` returns to idle.
- **Distance metric:** Chebyshev / square distance `max(|dx|, |dy|)` for leader distance, follow target validity, nearby-player visibility, and dashboard player distance.
- **Close enough:** if leader distance <= 1 (same tile or adjacent), `WAIT` with `follow_reason = "close enough to leader"`.
- **Catch-up:** only when leader distance >= 2, score walkable tiles exactly one Chebyshev step from the leader by known reachability/path cost, preferring reachable non-`blocked_tiles`; dangerous animal tiles (`avoid_targets`, dashboard `!`) are a soft penalty instead of a hard exclusion.
- **Retarget cooldown:** reuse a current follow target for a few ticks while it remains valid.

Path execution (`protocol_client._resolve_move_path`, `movement.walkable_path_with_diagnostics`):

- Diagonal straight-line prefix when clear; otherwise 8-way BFS.
- Dynamic relative offsets per `MOVE` message: **2** in follow or when danger/blockers affect the route; **6** default; **10** on clear straight/diagonal open paths in `collect` / `collect_stack`.
- Pathfinding merges `blocked_tiles` with danger tiles plus a **1-tile Chebyshev buffer** so routes do not step onto or adjacent to live animals.
- Cautious batching is triggered by danger **near the current route**, not merely because a threat is visible elsewhere on the map.
- Each path stores diagnostics in `observation.facts["last_path_diagnostics"]`: start/target/effective target, path length, method (`straight` or `bfs`), search radius, and failure reason when no route is found.
- Still one policy action per stationary frame; movement gating remains unchanged.

Wide collision (`movement.blocking_footprint_tiles`) uses the object origin plus horizontal `leftBlockingRadius` / `rightBlockingRadius`; vertical neighbors are not blocked by radius alone.

### Interaction adjacency (USE / PICK_UP / depot)

**Walking** may use diagonal steps (`movement.py` 8-way BFS). **Object interaction** does not:

- **USE**, **PICK_UP**, and **stack depot USE** only work on the **same tile or orthogonal neighbors (N/S/E/W)**.
- `interact_flow.py`: `can_interact_with_tile()`, `approach_tile_orthogonal()`, `decide_navigate_or_pickup()`, `decide_navigate_to_interact()`.
- Used by `movement_policy.py` (collect/stack/camp/knap/harvest), `skills.py` (forage, remembered landmarks), and `behaviors.py` (recipe gather).

### Collect / stack chat modes

`MovementFollowPolicy` also supports object-gathering commands:

- **`collect <item>`** — move to / pick up the nearest matching nearby object.
- **`collect stack <item>`** — gather loose items and matching piles to a depot tile beside the speaker; deposit **6** of that item via drop/use on the stack (default count; per-item stack limits like stone×10 / garlic×5 are deferred).
- Item matching uses `game_data.build_stack_collect_catalog()` (loose object + `"<name> pile"` pairs and transition target ids from sandbox `objects/` + `transitions/`). Chat text is case-insensitive (`collect stack limestone`, `COLLECT STACK STONE`, etc.). Unknown items fall back to name heuristics (`<item>` and `<item> pile`).
- Stack mode picks from **loose items and visible piles** (depot tile excluded), uses shared pickup reliability (stationary gate, short retry cooldown), **skips sources on danger tiles**, keeps the same source for several ticks to reduce zigzag retargeting, and uses longer open-path batches when the route is clear.
- `stop collect`, `stop follow`, and `idle` return to idle.

### Camp depot grid and `stock camp`

When **`set home here`** is applied, the bot also records a fixed **3×3 camp layout** (`camp_depot.py`):

- **Fire center** = well/home + **(0, +8)** (8 tiles north).
- **8 numbered depot slots** on the ring around the fire: **NW = 1**, then **clockwise** to **W = 8**.

| Slot | Item | Target |
|------|------|--------|
| 1 | stone | 10 |
| 2 | sharp stone | 6 |
| 3 | flint chip | 6 (drop-only; knap from Flint outcrop 133 → Flint Chips 150 → pick up chip 135) |
| 4 | wild onion | 6 |
| 5 | wild carrot | 6 |
| 6 | burdock | 6 |
| 7 | wild garlic | 6 |
| 8 | straight branch | 6 |

**`stock camp`** (chat-driven) fills all incomplete slots **opportunistically**: each tick picks the **nearest** visible source among all slots still needing items, carries to that slot’s fixed tile, deposits, repeats. Cancel with `idle` / `stop follow` / etc. Uses `game_data.build_camp_stack_rules()` merged into the stack catalog for non-standard pile names (`Pile of Sharp Stones`, etc.). **Dig-harvest** slots (burdock, wild carrot, flint) run automatically when plants/outcrops or dug/chip tiles are visible; harvest matching uses **object ids** (e.g. wild carrot plant 404 vs loose product 40 share a name). Prefers **nearby loose product** over distant dug/plant work. Drops surplus held items when a slot is already full.

### Danger tiles and map semantics

| Dashboard | Fact keys | Meaning |
|-----------|-----------|---------|
| `#` | `blocked_tiles`, `known_blocking_tiles` | Walking blockers plus movement-failure memory (FORCE, repeatedly unreachable targets) |
| `!` | `avoid_targets`, `danger_tiles` | Live dangerous animals recomputed each observation |

Detection (`danger.py` + `game_data.py`):

- Primary: sandbox object `deadlyDistance > 0` (wolf, mosquito swarm, wild boar, rattle snake, grizzly bear, etc.).
- Fallback: normalized OHOL names / phrases when game data is missing or an attacking variant has `deadlyDistance = 0` (e.g. `Attacking Rattle Snake`, `Mosquito Swarm#just bit`).

Consumers:

- **Pathfinding** — danger tiles + 1-tile buffer are hard-blocked.
- **Explore / survival** — danger tiles are hard-skipped.
- **Follow** — danger tiles are a soft penalty when scoring formation targets.
- **Collect / stack** — sources and depots on danger tiles are skipped.

Movement-feedback false positives (marking open ground as `!` during follow/collect) were removed: unreachable targets now go to `blocked_tiles` only.

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
| Move | `MOVE start_x start_y @seq dx1 dy1 [dx2 dy2 ...]#` — bot sends dynamic relative offsets per message; `_resolve_move_path()` uses `walkable_path_with_diagnostics()` when game data is loaded |
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

**Action tile (`_action_tile`):** coordinates sent in MOVE/SELF must match the server’s idea of where the player is. Updated on confirmed PU/PM — not optimistically advanced on MOVE send. While a move is in flight, stale self `PU` positions without `done_moving_seq` are ignored so the dashboard and `_action_tile` do not snap backward after a `PM`.

**Birth-relative coordinates:** map objects from MC/MX use **absolute** world coords; MOVE/PU/PM use coords **relative to spawn**. `WorldState.birth_tile` converts between them so pathfinding and nearby-object distance checks stay correct when spawning far from origin. For batched `PM`, the parser keeps both start and final coordinates; `birth_tile` is anchored from the PM start coordinate so the local map does not drift by the first batch offset.

**Move sequence:** PU field 12 is `done_moving_seq` (sequence number, not a boolean). `WorldState.move_in_flight()` blocks new MOVEs until the server confirms the step. After server **FORCE** (invalid path), bot waits for next **FM** before sending again (`_awaiting_force_ack`).

**Server time steps (`FM`):** each server tick ends with an **`FM`** frame. OHOL servers are **message-reactive**: step rate rises when clients send traffic (another player spamming actions nearby can push the bot to ~6+ steps/sec). With **`--frame-paced`** alone, the bot blocks on `FM` and may feel sluggish solo.

**`--planner-hz`:** `poll_for_window(1/N)` + keep-alive at `1/N` keeps the server stepping without a second player. `LiveSessionEngine` still decides once per planner tick; movement gating unchanged.

**World tick:** `WorldState.tick` advances on **`FM`** via `note_server_frame()` (policy settle/cooldown timers). Do not confuse with planner tick.

### Tick counters (dashboard header)

| Counter | Meaning |
|---------|---------|
| **planner tick** | `run-live` / `play` loop iterations (observe → decide → act) |
| **world tick** | `WorldState.tick` — server simulation steps (`FM` count) |
| **server frames** | `FM` messages received (`--frame-paced` / `poll_for_window`) |
| **KA pings** | keep-alive messages sent |

Each counter shows **`(+N/5s)`** — how much it rose over the last 5 seconds (extrapolated if the session is shorter). Healthy solo play with `--planner-hz 6`: planner, world, and server frames often near **+30/5s**.

**Movement gating:** the official client sends one action at a time and waits until movement finishes. The bot mirrors this: `action_blocker()` returns non-`None` while `is_stationary=false`; live policies return `WAIT`; `OholProtocolClient.send()` drops non-wait actions while moving, while a move is in-flight, or while awaiting FORCE ack.

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

**Stationary nuance:** PU field 12 (`done_moving_seq`) is a **move-finish sequence number** (> 0 when a step completed). Only matching finish PUs clear in-flight state and mark stationary. PM and outgoing MOVE set moving; a 30s timeout clears stale motion if no finish PU arrives. Repeatedly unreachable move targets and FORCE path tiles are remembered in `blocked_tiles` (dashboard `#`), not as danger marks.

**Age nuance:** Dashboard **planner tick** is the `run-live` loop counter; **world tick** is `WorldState.tick` (one per server `FM`). Age on the dashboard is a **live estimate** (`age + elapsed / invAgeRate`), not the planner tick. Babies cannot self-act below `NO_MOVE_AGE = 0.20` years (~3s at 15s/year).

---

## 9. Survival Planner (Legacy / Scenarios)

`run-live` and `play` use `MovementFollowPolicy` by default. The survival planner remains useful for scenario tests and future survival/autonomy work.

`SurvivalPlanner.decide()` priority:

1. **Being carried** → `WAIT` (no movement or actions)
2. **Still moving** (`not is_stationary`) → `WAIT` until current step finishes (`hunger.action_blocker`)
3. **Hungry** (`is_planner_hungry` — at least **one stomach pip missing**):
   - Holding food → `USE_SELF` (eat) unless blocked (`hunger.eat_blocker`: too young, not stationary, eat pending)
   - Holding non-food → `DROP` to free hands
   - Adjacent food (8-way) → `PICK_UP` even if that tile is in `avoid_targets` (danger tile under food)
   - Else nearest food → `MOVE_TO` (pathfinder sends a short path toward target or approach tile)
   - No visible food → **explore**: one step in a rotating direction, skipping `blocked_tiles`, dangerous animal tiles (`avoid_targets`), and `previous_tile` (anti ping-pong)
4. **Far from home** (> 12 tiles) → `MOVE_TO` home
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
| `planner tick N (+R/5s)` / `world tick M` / `server frames F` / `KA pings K` | Loop count, server `FM` steps, and keep-alive traffic, each with **per-5-second rate** |
| `Age: … (live estimate)` | Interpolated age; `Age at last PU` is raw server snapshot |
| `Stationary` / `Forage blocked by` | Must be stationary to eat; while moving, planner waits |
| `Held: …` | Object name and id; may show `pending server confirm` after pickup |
| `Held food: yes/no` | Whether planner will try `USE_SELF` |
| `Carried by: …` | Adult player id if being carried, else `nobody` |
| `Planner / Reason` | Last action and human-readable explanation |
| `Last path: …` | Path method, batch length, and reason/failure reason from the last planned move |
| `Blocked tiles` / `Danger tiles` | Counts of movement-failure blockers vs live animal tiles |
| `Danger nearby` | Preview of nearest dangerous object names and tiles |
| `Local Tile Map` | ASCII map around the bot (`B`, `L`, `T`, `C`, `#`, `!`, `*`, `f`, `o`, `p`) — `#` blocked, `!` dangerous animal |

If `Held` flips from pie → `nothing` while the in-game sprite still holds food, that was a **stale PU with `o_id=0`** — fixed by held-item latching (see section 12).

---

## 10. What Works (Verified)

- Private server starts on `localhost:8005`
- Python **HMAC login** → `ACCEPTED`; server log: `New player bot_001@local connected`
- **Persistent session:** read loop, periodic `KA`, graceful shutdown
- **Live bot visible** in world during `stay-alive` / `run-live`
- **World state:** player position (PU/PM), hunger (FX), map tiles (MC/MX), ~100+ tracked objects at spawn
- **Live movement loop:** `run-live` / `play` with dashboard; idle/follow policy driven by chat
- **Legacy planner loop:** forage / explore / return home / collect branches remains available for scenarios/future autonomy
- **Frame-paced loop (`--frame-paced`):** `wait_for_frame()` or hybrid with `--planner-hz`
- **`--planner-hz` solo stim:** fixed-rate poll + keep-alive so server steps stay fast without a second player
- **Collect stack (any item):** `collect stack <item>` with game-data catalog + pile/loose sources, depot beside speaker, default deposit count 6
- **Movement gating + batched MOVE paths:** verified live; pathfinding routes around `blocksWalking` trees and can send short cardinal/diagonal paths
- **Local movement map diagnostics:** dashboard renders a compact tile map around the bot and labels path, leader, target, blockers, danger tiles, food, objects, and players
- **Reachability-aware follow target selection:** adjacent leader tiles are scored by known path reachability before choosing a formation target
- **Danger-aware pathfinding:** live animals (`deadlyDistance` + name fallback) hard-block routes with a 1-tile buffer; dashboard `!` no longer comes from movement-feedback false positives
- **Dashboard rate counters:** `(+N/5s)` on planner tick, world tick, server frames, KA pings
- **Dynamic movement batching:** cautious 2-step batches in follow or near danger/blockers; up to 10-step open batches in clear `collect` / `collect_stack` routes
- **Stuck-on-tree fixes:** `blocked_tiles` memory, rotating explore, adjacent pickup, FORCE ack gating, birth-tile coords
- **`scripts/verify_bot_run.py`:** 15s default stuck detection (unchanged tile, spam target, invalid paths); scaled thresholds via `--seconds`
- **Manual control (`control` CLI):** walk N tiles in a direction from terminal REPL
- **Eat held food (verified live):** move → `USE` pick up → `SELF x y -1#` at **`_action_tile`** → FX food increase / `just_ate` PU
- **Self player id lock:** first solo PU or PM-after-MOVE; LN no longer overwrites id
- **Action tile sync:** MOVE/SELF use `_action_tile` so server accepts actions after multi-step moves
- **Stationary for eat:** pickup PUs no longer falsely mark “still moving”
- **Live age estimate:** field 16 + 17 interpolation; dashboard shows estimate vs last PU
- **Held-item latch:** stale PU with empty `o_id` no longer clears a confirmed hold mid-move
- **Pending pickup:** dashboard shows held item immediately after `PICK_UP` before PU confirms
- **Carried awareness:** negative holding on adult PU → baby waits
- **`run-live --forever`:** indefinite session until Ctrl+C or another stop condition
- **Early hunger:** forage when one food pip is missing (good for testing eat behavior)
- **verify-live** harness for say, move, eat behaviors
- Game data: ~4400 objects, transitions from sandbox
- Mock scenarios + unit tests (`tests/test_survival.py`, `test_protocol_client.py`, etc.)

---

## 11. What Does NOT Work Yet / Limitations

| Gap | Notes |
|-----|-------|
| Recipe / craft planner | No transition chains (sharp stone, fire, etc.) |
| Wide collision | Horizontal `leftBlockingRadius` / `rightBlockingRadius` v1 done; full server parity for unusual sprites not proven |
| Pathfinding polish | BFS + `blocksWalking`, diagonal prefixes, diagnostics, dynamic batching, horizontal wide collision, and danger-aware routing done; remaining: terrain/object movement costs, wider deadly buffers, full collision parity for unusual sprites |
| Mother-specific carry | Waits when **any** adult carries the bot, not only `mother_id` |
| `action-probe` | Does not always login before sending actions |
| Multi-bot live | `family.py` is skeleton only; user deferred second bot |
| Full map memory | `tile_objects` cache grows with server sends; working/long-term split is explicit but planner still uses `nearby_objects` only |
| Biome attractors / fixed regions | Landmarks only; `tile_biomes` is flat coords, no regional clustering yet |
| pytest in CI | May need `pip install pytest` locally |
| All food edge cases | Gooseberry/berry path verified; sparse biomes may starve during long explore |
| LN for lineage graph | **Done** — LN populates ancestry/eve id and relations; still must not set self player id |

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
| Bot stuck mid-move (frame-paced) | New `MOVE` every `FM` while still walking | `action_blocker` + wait until stationary; one movement decision per stationary frame |
| Bot stuck on tree / ping-pong | Explore always north; unreachable targets not remembered | Rotating explore, skip previous tile, adjacent pickup, pathfinding + `blocked_tiles` memory |
| False `!` marks on open ground during follow | Legacy movement-feedback wrote `avoid_targets` while idle or retargeting | `avoid_targets` now means animals only; movement failures go to `blocked_tiles` |
| Bot walked into wolf during collect stack | Danger tiles were not hard-blocked in pathfinding | Danger tiles + 1-tile buffer merged into path blocked set; collect stack skips danger sources |
| Invalid path + MOVE spam | FORCE + MOVE same tick; wrong coords | Await FORCE ack on FM; birth-relative coords; corner-cutting |
| Dashboard/map bot marker offset by first batched move | `birth_tile` was derived from batched PM final tile against the old relative start tile | Parse PM start coords and anchor `birth_tile` from PM start, then use PM final only as movement destination |
| Bot/map briefly moved forward then snapped back | Stale self PU without `done_moving_seq` overwrote newer PM movement progress | Ignore stale self PU positions while move is in flight; only sync confirmed/forced PU or PM progress |
| Bot sluggish solo, smooth when another player is active | OHOL server steps faster when it receives more client messages; lone bot sent KA only every 5s | Use `--planner-hz 6`; world tick now advances on `FM` not per PU |
| Stack collect settle/pickup slow when map quiet | Policy cooldowns used `WorldState.tick` which only rose on sparse PU traffic | `note_server_frame()` on `FM`; pair with `--planner-hz` for solo |
| Default `--tick-seconds 1` feels slow | Double `poll_until` (~2s per action) | Use `--frame-paced --planner-hz 6` |

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
| Movement gating + batched paths | Done |
| Obstacle-aware pathfinding (basic BFS) | Done |
| Local tile map + path diagnostics | Done |
| Reachability-aware follow targets | Done |
| Dynamic MOVE batch sizing | Done |
| Danger-aware routing (`deadlyDistance`, path blockers, collect-stack safety) | Done |
| Collect stack chat mode | Done (`collect stack <item>`, catalog from game_data) |
| Stuck avoidance + verify_bot_run.py | Done |
| Manual terminal control | Done |
| Terminal dashboard | Done |
| Scripted survival (mock scenarios) | Done |
| Game data parser | Done |
| Curriculum scenarios | Scaffold |
| Multi-agent family coordinator | Skeleton only |
| **Recipe / transition planner** | **In progress** — RecipeBehavior v1 gather + transition input lookup implemented; multi-step chains not implemented |
| Wide collision / pathfinding polish | Partial (BFS + blocksWalking + horizontal wide collision + danger-aware routing + dynamic batched diagonal paths + diagnostics) |
| Second live bot + coordination | Deferred |

---

## 14. Recommended Next Steps (Priority Order)

### 1. Recipe / transition planner (next slice)

Current: one-step transition producer lookup (`recipe_graph.py`) and opt-in gather behavior.

Next: multi-step chain search over transitions (goal -> prerequisite outputs -> gather/use/drop action plans), then fold planned action sequences into `RecipeBehavior`.

### 2. Pathfinding polish

Wider deadly buffers, remembered threats beyond working radius, terrain/object movement costs, tighter forest heuristics, and full server collision parity for unusual sprites. Basic danger-aware routing and up to 10-step clear-path batches are already in place. Reference plannerbot for ideas; see [reuse_decision.md](reuse_decision.md).

### 3. Richer carry / family logic

**LN lineage parsing is done** (`lineage.py`, `relationships.py`) — populates `mother_id`, genetic relations on dashboard/facts. Still optional: only wait when carried by mother (today: any adult). Feed baby detection via **FX** / responsible player fields if needed.

### 4. Second bot (when user wants)

`bot_002@local`, separate `stay-alive` / `run-live`, wire `family.py` roles over shared state or server log.

### 5. Hardening

- `action-probe` should login before actions
- `requirements.txt` + pytest in dev instructions
- Broader live tests (craft, die, respawn)
- Run `python scripts/verify_bot_run.py` after movement changes (`--seconds 60` for longer checks)

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
| Pathfinding | `movement.py`, `protocol_client._resolve_move_path()` |
| Local map diagnostics | `map_debug.py`, `dashboard.py`, `WorldState.to_observation()` |
| Follow / idle policy | `movement_policy.py` (+ `movement_chat.py`, `follow_target.py`, `stack_collect.py`) |
| Shared movement helpers | `tiles.py`, `spatial_queries.py`, `interact_flow.py`, `action_pending.py` |
| Follow smoke test | `scripts/verify_follow_mode.py` |
| Stuck detection smoke test | `scripts/verify_bot_run.py` |
| Frame-paced + planner Hz loop | `runner.py`, `protocol_client.poll_for_window()`, `--planner-hz` |
| Self id + action tile + birth tile | `protocol_client.py`, `world_state.py` (`birth_tile`, `to_absolute`) |
| World state / observations | `world_state.py`, `protocol_messages.py` |
| Survival logic | `planner.py`, `skills.py` |
| Eat / move blockers | `hunger.py` (`action_blocker`, `eat_blocker`), `serialize_action()` |
| Held-item state | `world_state.py` (`pending_held_object_id`, `latched_self_held_object_id`, `held_yum`) |
| Avoid / blocked / danger tiles | `world_state.py`, `danger.py`, `protocol_client._path_blocked_tiles_abs()`, `skills._explore_step()` |
| Collect / stack chat modes | `movement_policy.py`, `game_data.build_stack_collect_catalog()` |
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

# Terminal 2: live bot with dashboard (recommended solo)
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --planner-hz 6 --watch

# Same with play (interactive manual overrides)
python -m ohol_bot.cli play --planner-hz 6

# Manual control (no autopilot)
python -m ohol_bot.cli control --frame-paced

# Stuck-detection smoke test (server must be running; ~15s default)
python scripts/verify_bot_run.py
python scripts/verify_bot_run.py --seconds 60 --max-ticks 800

# Timed session (50 ticks)
python -m ohol_bot.cli run-live --max-ticks 50 --tick-seconds 1 --watch

# Short checks
python -m ohol_bot.cli login-probe
python -m ohol_bot.cli stay-alive --seconds 30 --watch
python -m ohol_bot.cli verify-live
python -m ohol_bot.cli run-scenario scenarios\find_food.json
```

---

*Last updated: June 2026 — generalized `collect stack <item>`, world tick on `FM`, dashboard `(+N/5s)` rates, `--planner-hz` for solo server stepping, danger-aware pathfinding, collect/stack pile sources and pickup reliability.*
