from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from .biomes import count_biomes_in_radius
from .game_data import OholGameData
from .model import Action, ActionType, ObjectState, Observation, PlayerState, Tile, step_toward
from .movement import next_walkable_step
from .spatial_memory import SpatialMemory, WORKING_RADIUS, remembered_target_fact
from .world_feedback import ActionFeedbackState
from .protocol_messages import (
    CravingMessage,
    FoodChangeMessage,
    LineageMessage,
    MapChangeMessage,
    MapChunkMessage,
    PlayerMovementMessage,
    PlayerUpdateMessage,
    ProtocolMessage,
)

MOVE_STATIONARY_TIMEOUT_SECONDS = 30.0


@dataclass
class WorldState:
    """Mutable live view built from streamed protocol messages."""

    tick: int = 0
    self_player_id: int | None = None
    home_tile: Tile | None = None
    players: dict[int, PlayerState] = field(default_factory=dict)
    tile_objects: dict[Tile, int] = field(default_factory=dict)
    tile_biomes: dict[Tile, int] = field(default_factory=dict)
    tile_floors: dict[Tile, int] = field(default_factory=dict)
    pending_held_object_id: int | None = None
    pending_held_food_value: int = 0
    latched_self_held_object_id: int | None = None
    latched_self_held_yum: bool = False
    expect_empty_hands: bool = False
    feedback: ActionFeedbackState = field(default_factory=ActionFeedbackState)
    self_age_base: float = 0.0
    self_inv_age_rate_seconds: float = 15.0
    self_age_set_at: float | None = None
    self_move_started_at: float | None = None
    birth_tile: Tile | None = None
    _prev_self_tile: Tile | None = None
    _unchanged_move_ticks: int = 0
    spatial_memory: SpatialMemory = field(default_factory=SpatialMemory)

    @property
    def blocked_tiles(self) -> set[Tile]:
        return self.feedback.blocked_tiles

    @property
    def avoid_targets(self) -> set[Tile]:
        return self.feedback.avoid_targets

    @property
    def blocked_target_attempts(self) -> dict[Tile, int]:
        return self.feedback.blocked_target_attempts

    @property
    def last_move_target(self) -> Tile | None:
        return self.feedback.last_move_target

    @last_move_target.setter
    def last_move_target(self, value: Tile | None) -> None:
        self.feedback.last_move_target = value

    @property
    def confirmed_move_seq(self) -> int:
        return self.feedback.confirmed_move_seq

    @property
    def pending_force_tile(self) -> Tile | None:
        return self.feedback.pending_force_tile

    @property
    def eat_pending(self) -> bool:
        return self.feedback.eat_pending

    def to_absolute(self, tile: Tile) -> Tile:
        if self.birth_tile is None:
            return tile
        return Tile(tile.x + self.birth_tile.x, tile.y + self.birth_tile.y)

    def to_relative(self, tile: Tile) -> Tile:
        if self.birth_tile is None:
            return tile
        return Tile(tile.x - self.birth_tile.x, tile.y - self.birth_tile.y)

    def maybe_set_birth_from_absolute(self, absolute: Tile, relative: Tile) -> None:
        if self.birth_tile is not None:
            return
        self.birth_tile = Tile(absolute.x - relative.x, absolute.y - relative.y)

    def note_move_sent(self, step: Tile, target: Tile, sequence: int) -> None:
        self.feedback.note_move_sent(step, target, sequence)
        self._unchanged_move_ticks = 0
        self._mark_self_moving()

    def note_force_truncation(self) -> None:
        self.feedback.note_force_truncation()

    def note_move_blocked(self, target: Tile) -> None:
        self.feedback.note_move_blocked(target)

    def note_move_step_failed(self) -> None:
        self.feedback.note_move_step_failed()

    def move_in_flight(self) -> bool:
        return self.feedback.move_in_flight()

    def note_outgoing_action(
        self,
        action: Action,
        observation: Observation,
        game_data: OholGameData | None = None,
    ) -> None:
        if action.type is ActionType.MOVE_TO:
            target = Tile(action.payload["x"], action.payload["y"])
            start = observation.self.tile
            if game_data is not None:
                start_abs = self.to_absolute(start)
                target_abs = self.to_absolute(target)
                blocked_abs = {
                    self.to_absolute(tile) for tile in self.blocked_tiles
                }
                next_abs = next_walkable_step(
                    start_abs,
                    target_abs,
                    self.tile_objects,
                    game_data.objects,
                    blocked_tiles=blocked_abs,
                )
                if next_abs is None:
                    self.note_move_blocked(target)
                    return
                next_tile = self.to_relative(next_abs)
            else:
                next_tile = step_toward(start, target)
            if next_tile != start:
                sequence = action.payload.get(
                    "sequence", self.feedback.last_outgoing_move_seq + 1
                )
                self.note_move_sent(next_tile, target, sequence)
            return

        if action.type is ActionType.PICK_UP:
            tile = Tile(action.payload["x"], action.payload["y"])
            picked = _object_at(observation, tile)
            if picked is not None:
                self.pending_held_object_id = picked.object_id
                self.pending_held_food_value = picked.food_value
                self.latched_self_held_object_id = picked.object_id
                self.expect_empty_hands = False
            self.spatial_memory.forget_tile(self.to_absolute(tile))
            return

        if action.type is ActionType.USE:
            if observation.self.held_object_id is not None or observation.self.is_holding_food:
                return
            tile = Tile(action.payload["target_x"], action.payload["target_y"])
            picked = _object_at(observation, tile)
            if picked is not None:
                self.pending_held_object_id = picked.object_id
                self.pending_held_food_value = picked.food_value
                self.latched_self_held_object_id = picked.object_id
                self.expect_empty_hands = False
            self.spatial_memory.forget_tile(self.to_absolute(tile))
            return

        if action.type is ActionType.USE_SELF:
            self.pending_held_object_id = None
            self.pending_held_food_value = 0
            self.expect_empty_hands = True
            self.feedback.note_use_self(observation.self.food_store)
            return

        if action.type is ActionType.DROP:
            self.pending_held_object_id = None
            self.pending_held_food_value = 0
            self.latched_self_held_object_id = None
            self.latched_self_held_yum = False
            self.expect_empty_hands = True
            self._clear_eat_pending()

    def apply(self, message: ProtocolMessage) -> None:
        self.tick += 1

        if isinstance(message, LineageMessage):
            pass
        elif isinstance(message, PlayerUpdateMessage):
            for entry in message.players:
                self._apply_player_update(entry)
            self._refresh_held_by_relationships()
            for entry in message.players:
                if entry.done_moving_seq > 0:
                    self._clear_held_by_on_drop(entry.player_id)
        elif isinstance(message, PlayerMovementMessage):
            for entry in message.players:
                if entry.player_id not in self.players:
                    continue
                if entry.x is None or entry.y is None:
                    continue
                player = self.players[entry.player_id]
                absolute = Tile(entry.x, entry.y)
                if entry.player_id == self.self_player_id:
                    self.maybe_set_birth_from_absolute(absolute, player.tile)
                    new_tile = self.to_relative(absolute)
                    if new_tile != player.tile:
                        self._mark_self_moving()
                else:
                    new_tile = absolute
                updates = {"tile": new_tile}
                self.players[entry.player_id] = replace(player, **updates)
        elif isinstance(message, FoodChangeMessage):
            if self.self_player_id is None:
                return
            player = self.players.get(self.self_player_id)
            if player is None:
                return
            self.feedback.maybe_clear_eat_pending_on_food_change(message.food_store)
            self.players[self.self_player_id] = replace(
                player,
                food_store=message.food_store,
                max_food_store=message.food_capacity,
                yum_bonus=message.yum_bonus,
                yum_multiplier=message.yum_multiplier,
            )
        elif isinstance(message, CravingMessage):
            if self.self_player_id is None:
                return
            player = self.players.get(self.self_player_id)
            if player is None:
                return
            self.players[self.self_player_id] = replace(
                player,
                craving_food_id=message.food_id,
                craving_yum_bonus=message.yum_bonus,
            )
        elif isinstance(message, MapChangeMessage):
            for change in message.changes:
                tile = Tile(change.x, change.y)
                if change.floor_id is not None:
                    self.tile_floors[tile] = change.floor_id
                self._ingest_map_object(tile, change.object_id)
        elif isinstance(message, MapChunkMessage):
            for cell in message.cells:
                tile = Tile(cell.x, cell.y)
                self.tile_biomes[tile] = cell.biome_id
                self.tile_floors[tile] = cell.floor_id
                self._ingest_map_object(tile, cell.object_id)

    def note_self_spawn(self) -> None:
        if self.self_player_id is None:
            return
        player = self.players.get(self.self_player_id)
        if player is not None and self.home_tile is None:
            self.home_tile = player.tile

    def to_observation(
        self,
        game_data: OholGameData | None = None,
        *,
        radius: int = 24,
    ) -> Observation:
        if self.self_player_id is None or self.self_player_id not in self.players:
            return Observation(
                tick=self.tick,
                self=PlayerState(
                    player_id=self.self_player_id or -1,
                    tile=Tile(0, 0),
                    age=0,
                    food_store=1,
                    max_food_store=1,
                ),
                facts={"world_state_ready": False, "tick": self.tick},
            )

        self_player = self._enrich_self_player(
            self.players[self.self_player_id],
            game_data,
        )
        previous_tile = self._prev_self_tile
        if self.feedback.last_move_target is not None:
            if self._prev_self_tile == self_player.tile:
                self._unchanged_move_ticks += 1
            else:
                self._unchanged_move_ticks = 0
            if self._unchanged_move_ticks >= 4:
                self.feedback.avoid_targets.add(self.feedback.last_move_target)
                self._unchanged_move_ticks = 0
        self._prev_self_tile = self_player.tile
        self._tick_eat_pending()
        center_abs = self.to_absolute(self_player.tile)
        memory_stats = self.spatial_memory.sync(
            center_abs,
            self.tile_objects,
            game_data,
            self.tick,
            tile_biomes=self.tile_biomes,
            radius=radius,
        )
        nearby_objects = self._object_states_from_working()
        nearest_remembered_food = self.spatial_memory.nearest_food(
            self.spatial_memory.long_term,
            center_abs,
        )
        nearest_remembered_collect = self.spatial_memory.nearest_named(
            self.spatial_memory.long_term,
            center_abs,
            names=set(),
            collect_landmarks=True,
        )
        nearby_players = tuple(
            player
            for player_id, player in self.players.items()
            if player_id != self.self_player_id
            and self_player.tile.distance_to(player.tile) <= radius
        )
        self_biome_id = self.tile_biomes.get(self.to_absolute(self_player.tile))
        self_floor_id = self.tile_floors.get(self.to_absolute(self_player.tile))
        nearby_biome_counts = count_biomes_in_radius(
            self.tile_biomes, self.to_absolute(self_player.tile), radius
        )
        self_biome_name = (
            game_data.biome_name(self_biome_id)
            if game_data is not None and self_biome_id is not None
            else None
        )

        return Observation(
            tick=self.tick,
            self=self_player,
            nearby_objects=nearby_objects,
            nearby_players=nearby_players,
            home=self.home_tile,
            self_biome_id=self_biome_id,
            self_floor_id=self_floor_id,
            facts={
                "world_state_ready": True,
                "tracked_players": len(self.players),
                "tracked_objects": len(self.tile_objects),
                "tracked_biome_tiles": len(self.tile_biomes),
                "tracked_floor_tiles": len(self.tile_floors),
                "held_latched_id": self.latched_self_held_object_id,
                "held_pending_id": self.pending_held_object_id,
                "eat_pending": self.feedback.eat_pending,
                "age_server_base": self.self_age_base,
                "age_seconds_per_year": self.self_inv_age_rate_seconds,
                "self_biome_name": self_biome_name,
                "nearby_biome_counts": nearby_biome_counts,
                "avoid_targets": tuple(
                    (tile.x, tile.y)
                    for tile in sorted(
                        self.feedback.avoid_targets, key=lambda t: (t.x, t.y)
                    )
                ),
                "birth_tile": (
                    {"x": self.birth_tile.x, "y": self.birth_tile.y}
                    if self.birth_tile is not None
                    else None
                ),
                "blocked_tiles": tuple(
                    (tile.x, tile.y)
                    for tile in sorted(
                        self.feedback.blocked_tiles, key=lambda t: (t.x, t.y)
                    )
                ),
                "previous_tile": (
                    {"x": previous_tile.x, "y": previous_tile.y}
                    if previous_tile is not None
                    else None
                ),
                "working_memory_count": memory_stats.working_count,
                "long_term_memory_count": memory_stats.long_term_count,
                "long_term_food_count": self.spatial_memory.long_term_food_count(),
                "memory_promoted_this_tick": memory_stats.promoted_this_tick,
                "memory_forgotten_this_tick": memory_stats.forgotten_this_tick,
                "long_term_food_preview": self.spatial_memory.long_term_food_preview(
                    center_abs
                ),
                "nearest_remembered_food": (
                    remembered_target_fact(
                        nearest_remembered_food,
                        center_abs,
                        self.to_relative,
                    )
                    if nearest_remembered_food is not None
                    else None
                ),
                "nearest_remembered_collect": (
                    remembered_target_fact(
                        nearest_remembered_collect,
                        center_abs,
                        self.to_relative,
                    )
                    if nearest_remembered_collect is not None
                    else None
                ),
                "remembered_collect_preview": self.spatial_memory.long_term_collect_preview(
                    center_abs
                ),
                "long_term_by_biome": self.spatial_memory.long_term_by_biome_counts(
                    game_data
                ),
            },
        )

    def _estimate_current_age(self) -> float:
        if self.self_age_set_at is None:
            return self.self_age_base
        elapsed = time.monotonic() - self.self_age_set_at
        age_rate_years_per_second = 1.0 / self.self_inv_age_rate_seconds
        return self.self_age_base + age_rate_years_per_second * elapsed

    def _resolve_self_stationary(self, player: PlayerState) -> PlayerState:
        if player.is_stationary:
            return player
        if self.self_move_started_at is None:
            self._set_self_stationary(True)
            return replace(self.players[self.self_player_id], is_stationary=True)
        if self.move_in_flight():
            elapsed = time.monotonic() - self.self_move_started_at
            if elapsed >= MOVE_STATIONARY_TIMEOUT_SECONDS:
                self.note_move_step_failed()
                self._mark_self_stationary()
                return replace(self.players[self.self_player_id], is_stationary=True)
            return player
        self._mark_self_stationary()
        return replace(self.players[self.self_player_id], is_stationary=True)

    def take_pending_force(self) -> Tile | None:
        return self.feedback.take_pending_force()

    def _mark_self_moving(self) -> None:
        self._set_self_stationary(False)
        self.self_move_started_at = time.monotonic()

    def _mark_self_stationary(self) -> None:
        self._set_self_stationary(True)
        self.self_move_started_at = None

    def _set_self_stationary(self, is_stationary: bool) -> None:
        if self.self_player_id is None:
            return
        player = self.players.get(self.self_player_id)
        if player is None:
            return
        self.players[self.self_player_id] = replace(player, is_stationary=is_stationary)

    def _clear_eat_pending(self) -> None:
        self.feedback.clear_eat_pending()

    def _tick_eat_pending(self) -> None:
        from .hunger import EAT_PENDING_TIMEOUT_TICKS
        self.feedback.tick_eat_pending(EAT_PENDING_TIMEOUT_TICKS)

    def _apply_player_update(self, entry) -> None:
        if entry.x is None or entry.y is None:
            return

        tile = Tile(entry.x, entry.y)
        existing = self.players.get(entry.player_id)
        food_store = existing.food_store if existing else 1
        max_food_store = existing.max_food_store if existing else 1
        age = entry.age if entry.age is not None else (existing.age if existing else 0.0)
        is_stationary = existing.is_stationary if existing else True
        if entry.player_id == self.self_player_id:
            if entry.force_position and entry.x is not None and entry.y is not None:
                self.feedback.note_force_position(
                    Tile(entry.x, entry.y),
                    entry.done_moving_seq,
                )
                self._mark_self_stationary()
                is_stationary = True
                tile = Tile(entry.x, entry.y)
            elif entry.done_moving_seq > 0:
                if self.feedback.note_move_confirmed(entry.done_moving_seq):
                    self._mark_self_stationary()
                    is_stationary = True
            if entry.age is not None:
                self.self_age_base = entry.age
                self.self_age_set_at = time.monotonic()
            if (
                entry.inv_age_rate_seconds_per_year is not None
                and entry.inv_age_rate_seconds_per_year > 0
            ):
                self.self_inv_age_rate_seconds = entry.inv_age_rate_seconds_per_year

        self.players[entry.player_id] = PlayerState(
            player_id=entry.player_id,
            tile=tile,
            age=age,
            food_store=food_store,
            max_food_store=max_food_store,
            held_object_id=self._resolve_held_object_id(entry, existing),
            held_baby_id=entry.held_baby_id,
            held_by_player_id=existing.held_by_player_id if existing else None,
            held_yum=self._resolve_held_yum(entry, existing),
            yum_bonus=existing.yum_bonus if existing else 0,
            yum_multiplier=existing.yum_multiplier if existing else 0,
            craving_food_id=existing.craving_food_id if existing else None,
            craving_yum_bonus=existing.craving_yum_bonus if existing else 0,
            is_stationary=is_stationary,
            mother_id=existing.mother_id if existing else None,
            lineage_id=existing.lineage_id if existing else None,
        )

        if entry.player_id == self.self_player_id and entry.just_ate:
            self._clear_eat_pending()

        if entry.player_id == self.self_player_id and self.home_tile is None:
            self.home_tile = tile

    def _refresh_held_by_relationships(self) -> None:
        carriers: dict[int, int] = {}
        for player_id, player in self.players.items():
            if player.held_baby_id is not None:
                carriers[player.held_baby_id] = player_id

        for baby_id, adult_id in carriers.items():
            baby = self.players.get(baby_id)
            if baby is not None and baby.held_by_player_id != adult_id:
                self.players[baby_id] = replace(baby, held_by_player_id=adult_id)

        for player_id, player in self.players.items():
            if player.held_by_player_id is not None and player_id not in carriers:
                self.players[player_id] = replace(player, held_by_player_id=None)

    def _clear_held_by_on_drop(self, player_id: int) -> None:
        player = self.players.get(player_id)
        if player is not None and player.is_being_carried:
            self.players[player_id] = replace(player, held_by_player_id=None)

    def _resolve_held_object_id(self, entry, existing: PlayerState | None) -> int | None:
        if entry.player_id != self.self_player_id:
            if not entry.holding_field_present:
                return existing.held_object_id if existing else None
            return entry.held_object_id

        if not entry.holding_field_present:
            return self._effective_self_held_id(existing)

        if entry.held_object_id is not None:
            self.pending_held_object_id = None
            self.pending_held_food_value = 0
            self.latched_self_held_object_id = entry.held_object_id
            self.expect_empty_hands = False
            return entry.held_object_id

        if entry.just_ate:
            self.latched_self_held_object_id = None
            self.expect_empty_hands = False
            return None

        if entry.held_yum and self.pending_held_object_id is not None:
            self.latched_self_held_object_id = self.pending_held_object_id
            self.pending_held_object_id = None
            self.pending_held_food_value = 0
            return self.latched_self_held_object_id

        if entry.done_moving_seq > 0 and not entry.held_yum:
            self.latched_self_held_object_id = None
            self.expect_empty_hands = False
            return None

        effective = self._effective_self_held_id(existing)
        if effective is not None:
            return effective

        return None

    def _effective_self_held_id(self, existing: PlayerState | None) -> int | None:
        if existing is not None and existing.held_object_id is not None:
            return existing.held_object_id
        if self.pending_held_object_id is not None:
            return self.pending_held_object_id
        if self.latched_self_held_object_id is not None:
            return self.latched_self_held_object_id
        return None

    def _resolve_held_yum(self, entry, existing: PlayerState | None) -> bool:
        if entry.player_id == self.self_player_id:
            if entry.held_yum:
                self.latched_self_held_yum = True
                return True
            if entry.just_ate:
                self.latched_self_held_yum = False
                return False
            if entry.done_moving_seq > 0 and entry.holding_field_present and entry.held_object_id is None:
                self.latched_self_held_yum = False
                return False
            if self.latched_self_held_yum:
                return True

        if not entry.holding_field_present:
            return existing.held_yum if existing else False

        if entry.held_object_id is not None:
            return entry.held_yum

        if existing is not None and existing.held_yum:
            return True

        return entry.held_yum

    def _enrich_self_player(
        self,
        player: PlayerState,
        game_data: OholGameData | None,
    ) -> PlayerState:
        player = replace(player, age=self._estimate_current_age())
        player = self._resolve_self_stationary(player)
        held_object_id, held_pending = self._resolve_display_held(player)
        held_yum = player.held_yum or self.latched_self_held_yum

        if game_data is None or held_object_id is None:
            held_food_value = (
                self.pending_held_food_value
                if held_pending and player.held_food_value <= 0
                else player.held_food_value
            )
            return replace(
                player,
                held_object_id=held_object_id,
                held_food_value=held_food_value,
                held_pending=held_pending,
                held_yum=held_yum,
            )

        obj = game_data.objects.get(held_object_id)
        if obj is None:
            return replace(
                player,
                held_object_id=held_object_id,
                held_pending=held_pending,
                held_yum=held_yum,
            )

        return replace(
            player,
            held_object_id=held_object_id,
            held_food_value=obj.food_value,
            held_object_name=obj.name,
            held_pending=held_pending,
            held_yum=held_yum or obj.food_value > 0,
        )

    def _resolve_display_held(self, player: PlayerState) -> tuple[int | None, bool]:
        if player.held_object_id is not None and player.held_object_id > 0:
            if (
                self.pending_held_object_id is not None
                and self.pending_held_object_id == player.held_object_id
            ):
                return player.held_object_id, True
            return player.held_object_id, False
        if self.pending_held_object_id is not None:
            return self.pending_held_object_id, True
        if self.latched_self_held_object_id is not None:
            return self.latched_self_held_object_id, False
        return None, False

    def _self_center_abs(self) -> Tile | None:
        if self.self_player_id is None:
            return None
        player = self.players.get(self.self_player_id)
        if player is None:
            return None
        return self.to_absolute(player.tile)

    def _ingest_map_object(self, abs_tile: Tile, object_id: int) -> None:
        if object_id <= 0:
            self.tile_objects.pop(abs_tile, None)
            self.spatial_memory.forget_tile(abs_tile)
            return
        self.tile_objects[abs_tile] = object_id
        self.spatial_memory.on_map_update(
            abs_tile,
            object_id,
            game_data=None,
            tick=self.tick,
            center_abs=self._self_center_abs(),
            tile_biomes=self.tile_biomes,
            radius=WORKING_RADIUS,
        )

    def _object_states_from_working(self) -> tuple[ObjectState, ...]:
        objects: list[ObjectState] = []
        for entry in self.spatial_memory.working.values():
            rel_tile = self.to_relative(entry.tile)
            objects.append(
                ObjectState(
                    object_id=entry.object_id,
                    name=entry.name,
                    tile=rel_tile,
                    food_value=entry.food_value,
                    biome_id=self.tile_biomes.get(entry.tile),
                    floor_id=self.tile_floors.get(entry.tile),
                )
            )
        return tuple(objects)

    def _nearby_objects(
        self,
        center: Tile,
        game_data: OholGameData | None,
        radius: int,
    ) -> tuple[ObjectState, ...]:
        """Legacy helper: sync spatial memory and return working-memory objects."""
        center_abs = self.to_absolute(center)
        self.spatial_memory.sync(
            center_abs,
            self.tile_objects,
            game_data,
            self.tick,
            tile_biomes=self.tile_biomes,
            radius=radius,
        )
        return self._object_states_from_working()

    def biome_at(self, tile: Tile) -> int | None:
        return self.tile_biomes.get(tile)

    def floor_at(self, tile: Tile) -> int | None:
        return self.tile_floors.get(tile)


def _object_at(observation: Observation, tile: Tile) -> ObjectState | None:
    for obj in observation.nearby_objects:
        if obj.tile == tile:
            return obj
    return None
