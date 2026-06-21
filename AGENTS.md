# Agent Onboarding — OHOL Bot

Read **[docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md)** first. It is the full project context document for fresh sessions.

## One-line goal

Build Python bots that play One Hour One Life on a local private server, survive, and eventually cooperate as a family.

## Current focus

**Single live bot** with a movement-first idle/follow loop (`run-live --forever`, `play`). The protocol client stays connected, tracks world state from packets, and runs `MovementFollowPolicy` by default. Legacy survival behavior still exists for scenarios/tests and can forage, pick up, **eat held food via `USE_SELF`**, return home, collect branches, and wait when carried.

**Movement:** one movement decision per planner tick; the client waits until **stationary** before sending non-`WAIT` actions. `MOVE` messages may carry a dynamic batched path (2–10 relative offsets per message, including diagonals). **Obstacle-aware pathfinding** (`movement.py`) routes around `blocksWalking` objects using 8-way BFS, diagonal straight-line prefixes, birth-relative coordinates, corner-cutting rules, and horizontal `leftBlockingRadius` / `rightBlockingRadius` footprints.

**Interaction adjacency (important):** walking may use diagonals, but **USE, PICK_UP, and stack depot USE** only work on the **same tile or orthogonal neighbors (N/S/E/W)** — not diagonally. `interact_flow.py` enforces this via `can_interact_with_tile()` and `approach_tile_orthogonal()` for collect/stack/camp pickup, depot deposit, knap, and dig-harvest USE steps. `skills.py` / `behaviors.py` use the same helpers for forage and recipe gather.

**Tile semantics on the dashboard map:** `#` = `blocked_tiles` (trees, FORCE path tiles, repeatedly unreachable targets). `!` = dangerous animals from `avoid_targets` / `danger_tiles` (wolf, bear, wild boar, mosquito swarm, rattle snake, etc.). Danger is detected from sandbox `deadlyDistance` in `game_data.py` with OHOL name-variant fallback in `danger.py`. Pathfinding hard-blocks danger tiles plus a 1-tile Chebyshev buffer so the bot does not walk onto or adjacent to live threats.

**Batch sizing:** follow uses cautious 2-step batches; `collect` / `collect_stack` may use up to 10 steps on clear straight paths. Cautious batches trigger when FORCE/unreachable memory exists, blockers are nearby, or danger is near the current route — not merely because a wolf is visible elsewhere on the map.

**Follow:** in-game `follow` from another player starts following that speaker; `stop follow` / `idle` returns to idle. Follow uses Chebyshev distance: the bot waits when on the leader's tile or adjacent (distance <= 1), and only moves when distance >= 2 toward a walkable tile exactly one step from the leader. Danger tiles are a soft penalty for formation targets, not a hard ban.

**Collect / stack:** `collect <item>` and **`collect stack <item>`** (e.g. `stone`, `limestone`) are chat-driven modes in `movement_policy.py`. **`make sharp stone`** finds loose **Stone** (round stone), picks it up, and **USE**s it on **Big Hard Rock** (orthogonal adjacency required). **Dig harvest** (burdock, wild carrot, flint): hold sharp stone (or knap one first), **USE** on the source tile, **drop** the tool when needed, **USE** the intermediate tile (dug plant / flint chips) to gather, then pick up/deposit. Wild carrot stages are distinguished **by object id** (plant 404/36, dug 39, loose product 40) — not by shared name. Flint: **USE sharp stone on Flint outcrop (133)** → **Flint Chips (150)** → gather **Flint Chip (135)** → drop at camp slot (drop-only). Stack mode gathers loose items and matching piles to a depot beside the speaker, deposits **6** by default (per-item stack limits deferred), uses `game_data.build_stack_collect_catalog()` + `harvest.py`, skips danger-tile sources, prefers **nearby loose product** over distant dug/plant work when both are visible, and reuses the same source briefly to reduce zigzag. **`set home here`** snaps home to the nearest well/spring (or home marker) within 16 tiles of the speaker; the surrounding **12-tile** area counts as home (`home.py`). It also records a **camp depot grid**: fire tile **8 tiles north** of the well, with **8 numbered slots** (NW=1, clockwise) for fixed stack depots (`camp_depot.py`). **`stock camp`** fills all slots opportunistically — always gathers the **nearest** visible item for any incomplete slot (stone×10, sharp stone×6, flint chip×6 drop-only, wild onion/carrot/burdock/garlic×6, straight branch×6); burdock/carrot/flint run the dig-harvest flow automatically. Drops surplus items when a slot is already full.

**Pacing (important for solo play):** OHOL servers step faster when they receive more client messages. **`--planner-hz 6`** runs a fixed 6 Hz loop, polls the socket, and sends keep-alive at the same rate so the server keeps stepping without a second player nearby. Pair with **`--frame-paced`**. **World tick** (`WorldState.tick`) advances on server **`FM`** frames (policy settle/cooldown timers). Dashboard shows **(+N/5s)** rate counters for planner tick, world tick, server frames, and KA pings.

**Lineage / relationships:** **LN** packets populate per-player ancestry and eve id (`lineage.py`). `relationships.py` mirrors in-game `getRelationName` (mother, sibling, niece, cousin, distant relative). Dashboard and `observation.facts` expose `nearby_relations`, `self_mother_id`, and race from `display_id` when object defs include `race=`. **Do not** use LN to lock self player id.

**Verified on private server:** forage → pick up → eat loop (e.g. Gooseberry). Run **`scripts/verify_bot_run.py`** after movement changes to catch stuck-on-tree regressions.

**Manual control:** `python -m ohol_bot.cli control` — interactive REPL to walk N tiles east/south/etc. without the autopilot planner.

**Not started yet:** detecting existing pile height on camp slots at start, auto-crafting sharp stones inside `stock camp`, full recipe/transition planner (fire), multi-bot family coordination.

## Before you code

1. Server must be running: `.\scripts\run_private_server.ps1`
2. Python path: `$env:PYTHONPATH='src'`
3. Do not edit `Program Files` or `.cursor/plans/*.plan.md`
4. Do not git commit unless the user asks
5. After movement/pathfinding changes, run: `python scripts/verify_bot_run.py` (15s default; use `--seconds 60` for a longer check)

## Bot credentials (sandbox)

- email: `bot_001@local`
- account_key: `aaaa`
- client_id: `client_mariusbottest`
- server_password: `testPassword`
- server: `localhost:8005`

## Main files

| File | Role |
|------|------|
| `src/ohol_bot/protocol_client.py` | `OholProtocolClient` — login, read loop, keep-alive, `poll_for_window`, `wait_for_frame`, action send gating |
| `src/ohol_bot/world_state.py` | Mutable state from PU/PM/FX/MC/MX → `Observation`; `note_server_frame()` on `FM`; blocked/danger tiles, held latch, age, stationary |
| `src/ohol_bot/danger.py` | Dangerous animal detection (`deadlyDistance` + name fallback), path blockers, route-near checks |
| `src/ohol_bot/movement.py` | BFS pathfinding, batched diagonal paths, `resolve_approach_tile`, corner-cutting, `blocksWalking`, horizontal wide collision |
| `src/ohol_bot/home.py` | Well/spring home center, 12-tile home area |
| `src/ohol_bot/movement_policy.py` | MovementFollowPolicy orchestrator (idle/follow/collect/stack/camp) |
| `src/ohol_bot/movement_chat.py` | Chat command parsing for movement modes |
| `src/ohol_bot/follow_target.py` | Follow formation target scoring/selection |
| `src/ohol_bot/stack_collect.py` | Stack/collect/camp runtime state and helpers |
| `src/ohol_bot/interact_flow.py` | Orthogonal interact adjacency, approach tiles, navigate/pickup/drop/empty-hands |
| `src/ohol_bot/action_pending.py` | PendingAction retry/settle timers |
| `src/ohol_bot/tiles.py` | Chebyshev/adjacency, fact tile parsing, danger_tiles() |
| `src/ohol_bot/spatial_queries.py` | nearest_object(), object_at_tile() |
| `src/ohol_bot/object_names.py` | Item name normalization and stone/rock matchers |
| `src/ohol_bot/collect_rules.py` | Typed HarvestRule / StackCollectRule dataclasses |
| `src/ohol_bot/hunger.py` | Hunger threshold, `action_blocker` / eat blockers (age, moving, eat pending) |
| `src/ohol_bot/runner.py` | `LiveSessionEngine` — `--frame-paced`, `--planner-hz`, observe/decide/act loop |
| `src/ohol_bot/protocol_messages.py` | Packet parser (PU, PM, FX, MC, CM, …); `done_moving_seq` |
| `src/ohol_bot/planner.py` | `SurvivalPlanner` — hunger, home, branches, carried-wait |
| `src/ohol_bot/spatial_memory.py` | Working + long-term object landmarks (absolute); biome_id per tile |
| `src/ohol_bot/resource_memory.py` | Branch/tree landmark matching for collect navigation |
| `src/ohol_bot/skills.py` | Forage, explore, return home, collect; remembered food/branches when out of range |
| `src/ohol_bot/manual_control.py` | Interactive terminal control (`control` CLI) |
| `src/ohol_bot/naming.py` | Chat naming phrases, assigned names from lifeLog |
| `src/ohol_bot/lineage.py` | LN ancestry storage; enrich `mother_id` / `lineage_id` / race |
| `src/ohol_bot/relationships.py` | Genetic relation labels vs self (`your sister`, etc.) |
| `src/ohol_bot/game_data.py` | Objects/transitions; `build_stack_collect_catalog()` + camp stack rules |
| `src/ohol_bot/camp_depot.py` | Camp fire + 8-slot depot grid on `set home here` |
| `src/ohol_bot/harvest.py` | Dig-harvest rules for burdock/wild carrot/flint (sharp stone workflow; id-based stages) |
| `src/ohol_bot/dashboard.py` | Terminal dashboard for `--watch`; per-5s rate counters |
| `src/ohol_bot/cli.py` | `run-live`, `control`, `stay-alive`, `verify-live`, probes; `--planner-hz` |
| `scripts/verify_bot_run.py` | 15s default movement smoke test; `--seconds 60 --max-ticks 800` for longer runs |
| `scripts/verify_follow_mode.py` | Live follow smoke test against a known leader player id |
| `config/private_server.json` | Server sandbox settings |
| `config/local_clients.json` | Bot client credentials |

## Run the live bot (two terminals)

**Terminal 1 — server:**

```powershell
.\scripts\run_private_server.ps1
```

**Terminal 2 — bot with dashboard (recommended for solo smoothness):**

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli run-live --forever --frame-paced --planner-hz 6 --watch
```

Use **`--frame-paced`** for server-`FM`-aligned stepping. Add **`--planner-hz 6`** so the server keeps stepping when no other player is nearby (message-reactive server). Use **`--tick-seconds N`** only without frame-paced/planner-hz. Use **`--forever`** to run until Ctrl+C. With `--watch`, Ctrl+C leaves the dashboard visible; a short summary prints and the full run is overwritten to `.ohol_runtime/logs/last_run.json` (tail of actions, size-capped).

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
python scripts/verify_bot_run.py
# longer check: python scripts/verify_bot_run.py --seconds 60 --max-ticks 800
```

**Server won't start (`map.db` / KissDB error):** kill stale `OneLifeServer.exe`, delete `.ohol_runtime\server\map.db*` and `mapTime.db`, restart.

## Verify login only

```powershell
$env:PYTHONPATH='src'
python -m ohol_bot.cli login-probe
```

Expect `ACCEPTED`. For a short persistent session: `stay-alive --seconds 30 --watch`.
