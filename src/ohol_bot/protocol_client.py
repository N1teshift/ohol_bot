from __future__ import annotations

import socket
import time
from hmac import new as hmac_new
from hashlib import sha1
from dataclasses import dataclass

from .client import BotClient
from .game_data import OholGameData, load_game_data
from .model import Action, ActionType, Observation, PlayerState, Tile, step_toward
from .movement import next_walkable_step
from .protocol_messages import (
    CompressedMessage,
    CravingMessage,
    FoodChangeMessage,
    LineageMessage,
    MapChangeMessage,
    MapChunkMessage,
    PlayerMovementMessage,
    PlayerSaysMessage,
    PlayerUpdateMessage,
    ProtocolMessage,
    ProtocolMessageType,
    ServerLoginMessage,
    parse_protocol_message,
)
from .protocol_framing import ProtocolFrameReader
from .world_state import WorldState


@dataclass(frozen=True, slots=True)
class ProtocolCredentials:
    email: str
    account_key: str
    client_id: str = "ohol_bot"
    server_password: str = ""
    tutorial: bool = False
    name: str = "bot_001"


@dataclass(frozen=True, slots=True)
class StayAliveResult:
    connected_seconds: float
    self_player_id: int | None
    final_tile: Tile
    message_counts: dict[str, int]
    sent_keep_alives: int
    actions_sent: int


class OholProtocolProbe(BotClient):
    """First raw-socket probe for private-server protocol experiments.

    This class intentionally keeps the protocol messages visible and simple.
    The exact OHOL handshake still needs to be confirmed against the official
    client source/logs, so failed probes are expected while we map the protocol.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8005,
        credentials: ProtocolCredentials | None = None,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.host = host
        self.port = port
        self.credentials = credentials or ProtocolCredentials(
            email="bot_001@local",
            account_key="aaaa",
            client_id="client_mariusbottest",
            server_password="testPassword",
        )
        self.timeout_seconds = timeout_seconds
        self.socket: socket.socket | None = None
        self.sent_messages: list[str] = []
        self.received_messages: list[bytes] = []
        self.parsed_messages: list[ProtocolMessage] = []
        self.current_tile = Tile(0, 0)
        self.move_sequence = 0
        self._frame_reader = ProtocolFrameReader()

    def connect(self) -> None:
        if self.socket is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout_seconds)
        sock.settimeout(self.timeout_seconds)
        self.socket = sock

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self._frame_reader = ProtocolFrameReader()

    def login_probe(self) -> None:
        self.connect()
        # OHOL servers greet clients with SN before accepting LOGIN.
        self.read_messages()
        challenge = self._latest_challenge()
        self._send_message(build_login_message(self.credentials, challenge=challenge))

    def observe(self) -> Observation:
        return Observation(
            tick=0,
            self=PlayerState(
                player_id=-1,
                tile=self.current_tile,
                age=0,
                food_store=0,
                max_food_store=1,
            ),
            facts={"protocol_probe": True, "connected": self.socket is not None},
        )

    def send(self, action: Action) -> None:
        self.connect()
        self._send_message(serialize_action(action, self))

    def try_read(self, max_bytes: int = 4096) -> bytes:
        if self.socket is None:
            return b""
        try:
            data = self.socket.recv(max_bytes)
        except socket.timeout:
            return b""
        if not data:
            raise ConnectionError("Server closed the connection")
        self.received_messages.append(data)
        self._ingest_bytes(data)
        return data

    def read_messages(self, max_bytes: int = 8192) -> tuple[ProtocolMessage, ...]:
        self.try_read(max_bytes=max_bytes)
        return tuple(self.parsed_messages)

    def _ingest_bytes(self, data: bytes) -> tuple[ProtocolMessage, ...]:
        messages: list[ProtocolMessage] = []
        for frame in self._frame_reader.ingest(data):
            message = parse_protocol_message(frame)
            messages.append(message)
            self.parsed_messages.append(message)
        return tuple(messages)

    def _send_message(self, message: str) -> None:
        if self.socket is None:
            raise RuntimeError("Protocol probe is not connected")
        framed = ensure_protocol_frame(message)
        self.sent_messages.append(framed)
        self.socket.sendall(framed.encode("utf-8"))

    def _latest_challenge(self) -> str | None:
        challenge = None
        for message in self.parsed_messages:
            if isinstance(message, ServerLoginMessage):
                challenge = message.challenge or challenge
        return challenge


class OholProtocolClient(OholProtocolProbe):
    """Persistent OHOL protocol session with keep-alive and self-player tracking."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8005,
        credentials: ProtocolCredentials | None = None,
        timeout_seconds: float = 3.0,
        keep_alive_interval_seconds: float = 5.0,
        game_data: OholGameData | None = None,
        game_data_root: str | None = None,
    ) -> None:
        super().__init__(host, port, credentials, timeout_seconds)
        self.keep_alive_interval_seconds = keep_alive_interval_seconds
        self.game_data = game_data
        if self.game_data is None and game_data_root is not None:
            self.game_data = load_game_data(game_data_root)
        self.world_state = WorldState()
        self.self_player_id: int | None = None
        self.logged_in = False
        self.rejected = False
        self._last_keep_alive_at = 0.0
        self._message_counts: dict[str, int] = {}
        self._sent_keep_alives = 0
        self._actions_sent = 0
        self._last_observation: Observation | None = None
        self._self_player_id_locked = False
        self._awaiting_move_self_confirm = False
        self._action_tile = Tile(0, 0)
        self.frame_paced = False
        self.server_frames = 0
        self._awaiting_force_ack = False

    def login(self, timeout_seconds: float = 15.0) -> None:
        self.connect()
        deadline = time.monotonic() + timeout_seconds

        while self._latest_challenge() is None and time.monotonic() < deadline:
            self._poll_once()
        if self._latest_challenge() is None:
            raise RuntimeError("Timed out waiting for server login challenge (SN)")

        self._send_message(
            build_login_message(self.credentials, challenge=self._latest_challenge())
        )

        while not self.logged_in and not self.rejected and time.monotonic() < deadline:
            self._poll_once()

        if self.rejected:
            raise RuntimeError("Server rejected login")
        if not self.logged_in:
            raise RuntimeError("Timed out waiting for ACCEPTED after LOGIN")

        # Drain the initial spawn burst so player id/tile are available quickly.
        burst_deadline = time.monotonic() + 3.0
        while time.monotonic() < burst_deadline:
            messages = self._poll_once()
            if self.self_player_id is not None and self.world_state.players:
                break
            if not messages:
                time.sleep(0.05)
        self.world_state.note_self_spawn()

    def poll_until(self, timeout_seconds: float = 1.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._poll_once()
            self._maybe_send_keep_alive()
            time.sleep(0.05)

    def wait_for_frame(self, timeout_seconds: float = 30.0) -> bool:
        """Block until the server sends FM (end of one server time step).

        Returns False if no frame arrives before timeout (connection may be idle).
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            messages = self._poll_once()
            self._maybe_send_keep_alive()
            if _batch_has_frame(messages):
                self.server_frames += 1
                return True
            time.sleep(0.002)
        return False

    def wait_until_stationary(self, timeout_seconds: float = 30.0) -> bool:
        """Poll until the bot is standing still and no move is in flight."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._poll_once()
            self._maybe_send_keep_alive()
            if self.self_player_id is not None:
                self.world_state.self_player_id = self.self_player_id
            observation = self.world_state.to_observation(self.game_data)
            self.current_tile = observation.self.tile
            self._last_observation = observation
            if observation.self.is_stationary and not self.world_state.move_in_flight():
                return True
            time.sleep(0.002)
        return False

    def stay_alive(
        self,
        duration_seconds: float | None = None,
        *,
        say_once: str | None = None,
        move_to: Tile | None = None,
        watch: bool = False,
        watch_interval_seconds: float = 0.5,
    ) -> StayAliveResult:
        if not self.logged_in:
            self.login()

        start = time.monotonic()
        said = False
        moved = False
        last_action: Action | None = None
        last_watch_at = 0.0
        tick = 0

        if watch:
            from .dashboard import format_dashboard, print_dashboard

        try:
            while True:
                if duration_seconds is not None and time.monotonic() - start >= duration_seconds:
                    break

                self._poll_once()
                self._maybe_send_keep_alive()

                if say_once and not said:
                    self.say(say_once)
                    last_action = Action(ActionType.SAY, {"text": say_once})
                    said = True

                if move_to is not None and not moved and self.self_player_id is not None:
                    self.move_to(move_to)
                    last_action = Action(ActionType.MOVE_TO, {"x": move_to.x, "y": move_to.y})
                    moved = True

                if watch:
                    now = time.monotonic()
                    if now - last_watch_at >= watch_interval_seconds:
                        tick += 1
                        observation = self.observe()
                        print_dashboard(
                            format_dashboard(
                                self,
                                observation,
                                last_action=last_action,
                                tick=tick,
                                mode="stay-alive",
                                elapsed_seconds=now - start,
                            )
                        )
                        last_watch_at = now

                time.sleep(0.05)
        except (KeyboardInterrupt, ConnectionError):
            pass
        finally:
            self.close()

        return StayAliveResult(
            connected_seconds=time.monotonic() - start,
            self_player_id=self.self_player_id,
            final_tile=self.current_tile,
            message_counts=dict(self._message_counts),
            sent_keep_alives=self._sent_keep_alives,
            actions_sent=self._actions_sent,
        )

    def send(self, action: Action) -> None:
        if action.type is ActionType.WAIT:
            if not self.frame_paced:
                time.sleep(0.25 * action.payload.get("ticks", 1))
            return
        if (
            self._last_observation is not None
            and not self._last_observation.self.is_stationary
        ):
            return
        if self.world_state.pending_force_tile is not None:
            return
        if self._awaiting_force_ack:
            return
        if self.world_state.move_in_flight():
            return
        if action.type is ActionType.MOVE_TO:
            if not self._self_player_id_locked:
                self._awaiting_move_self_confirm = True
            target = Tile(action.payload["x"], action.payload["y"])
            self.world_state.last_move_target = target
            if self.game_data is not None:
                start = self._action_tile
                step = self._resolve_move_step(start, target)
                if step is None or (step == start and start != target):
                    self.world_state.note_move_blocked(target)
                    self.world_state.last_move_target = target
                    return
                action = Action(
                    ActionType.MOVE_TO,
                    {
                        **action.payload,
                        "sequence": self.move_sequence + 1,
                    },
                )
        if self._last_observation is not None:
            self.world_state.note_outgoing_action(
                action, self._last_observation, self.game_data
            )
        super().send(action)
        self._actions_sent += 1

    def observe(self) -> Observation:
        self._poll_once()
        self._maybe_send_keep_alive()
        if self.self_player_id is not None:
            self.world_state.self_player_id = self.self_player_id
        observation = self.world_state.to_observation(self.game_data)
        player = observation.self
        self.current_tile = player.tile
        self._last_observation = observation
        return observation

    def _resolve_move_step(self, start: Tile, target: Tile) -> Tile | None:
        if self.game_data is None:
            return step_toward(start, target)
        start_abs = self.world_state.to_absolute(start)
        target_abs = self.world_state.to_absolute(target)
        blocked_abs = {
            self.world_state.to_absolute(tile)
            for tile in self.world_state.blocked_tiles
        }
        from .movement import resolve_approach_tile

        destination_abs = resolve_approach_tile(
            target_abs,
            start_abs,
            self.world_state.tile_objects,
            self.game_data.objects,
            blocked_tiles=blocked_abs,
        )
        if destination_abs is None:
            return None
        step_abs = next_walkable_step(
            start_abs,
            destination_abs,
            self.world_state.tile_objects,
            self.game_data.objects,
            blocked_tiles=blocked_abs,
        )
        if step_abs is None:
            return None
        return self.world_state.to_relative(step_abs)

    def _maybe_lock_self_player_id(self, player_id: int) -> None:
        if self._self_player_id_locked:
            return
        self.self_player_id = player_id
        self.world_state.self_player_id = player_id
        self._self_player_id_locked = True

    def _sync_self_tile(self, tile: Tile) -> None:
        self.current_tile = tile
        self._action_tile = tile

    def _poll_once(self) -> tuple[ProtocolMessage, ...]:
        before = len(self.parsed_messages)
        self.try_read()
        new_messages = tuple(self.parsed_messages[before:])
        for message in new_messages:
            self._dispatch_message(message)
        return new_messages

    def _dispatch_message(self, message: ProtocolMessage) -> None:
        self._message_counts[message.type.value] = (
            self._message_counts.get(message.type.value, 0) + 1
        )

        if message.type is ProtocolMessageType.ACCEPTED:
            self.logged_in = True
        elif message.type is ProtocolMessageType.REJECTED:
            self.rejected = True
        elif message.type is ProtocolMessageType.FRAME:
            if self._awaiting_force_ack:
                self._awaiting_force_ack = False
        elif isinstance(message, LineageMessage):
            pass
        elif isinstance(message, (PlayerUpdateMessage, PlayerMovementMessage, PlayerSaysMessage, FoodChangeMessage, CravingMessage, MapChangeMessage, MapChunkMessage)):
            self.world_state.apply(message)
            if isinstance(message, PlayerUpdateMessage):
                self._sync_self_from_player_updates(message)
                self._maybe_send_pending_force()
            elif isinstance(message, PlayerMovementMessage):
                self._sync_self_from_movement(message)
        elif isinstance(message, CompressedMessage):
            for nested in message.decompressed:
                self._dispatch_message(nested)

    def _sync_self_from_player_updates(self, message: PlayerUpdateMessage) -> None:
        if not self._self_player_id_locked and len(message.players) == 1:
            self._maybe_lock_self_player_id(message.players[0].player_id)

        for entry in message.players:
            if entry.player_id == self.self_player_id:
                if entry.x is not None and entry.y is not None:
                    self._sync_self_tile(Tile(entry.x, entry.y))

    def _sync_self_from_movement(self, message: PlayerMovementMessage) -> None:
        for entry in message.players:
            if (
                not self._self_player_id_locked
                and self._awaiting_move_self_confirm
            ):
                self._maybe_lock_self_player_id(entry.player_id)
                self._awaiting_move_self_confirm = False
            if entry.player_id == self.self_player_id:
                if entry.x is not None and entry.y is not None:
                    self._sync_self_tile(Tile(entry.x, entry.y))

    def _maybe_send_pending_force(self) -> None:
        force_tile = self.world_state.take_pending_force()
        if force_tile is None:
            return
        self._send_message(f"FORCE {force_tile.x} {force_tile.y}")
        self._sync_self_tile(force_tile)
        self.move_sequence = self.world_state.confirmed_move_seq
        self._awaiting_force_ack = True
        self._actions_sent += 1

    def _maybe_send_keep_alive(self) -> None:
        now = time.monotonic()
        if now - self._last_keep_alive_at < self.keep_alive_interval_seconds:
            return
        self._send_message("KA 0 0")
        self._sent_keep_alives += 1
        self._last_keep_alive_at = now


def _batch_has_frame(messages: tuple[ProtocolMessage, ...]) -> bool:
    for message in messages:
        if message.type is ProtocolMessageType.FRAME:
            return True
        if isinstance(message, CompressedMessage) and _batch_has_frame(message.decompressed):
            return True
    return False


def build_login_message(credentials: ProtocolCredentials, challenge: str | None = None) -> str:
    server_password_hash = _auth_hash(credentials.server_password, challenge)
    account_key_hash = _auth_hash(_pure_account_key(credentials.account_key), challenge)
    tutorial_flag = 1 if credentials.tutorial else 0
    return (
        f"LOGIN {credentials.client_id} {credentials.email:<80} "
        f"{server_password_hash} {account_key_hash} {tutorial_flag}#"
    )


def _auth_hash(secret: str, challenge: str | None) -> str:
    if challenge is None:
        return sha1(secret.encode("utf-8")).hexdigest()
    return hmac_new(secret.encode("utf-8"), challenge.encode("utf-8"), sha1).hexdigest()


def _pure_account_key(account_key: str) -> str:
    return account_key.replace("-", "").strip()


def ensure_protocol_frame(message: str) -> str:
    return message if message.endswith("#") else f"{message}#"


def _resolve_move_step(
    start: Tile,
    target: Tile,
    client: OholProtocolProbe | None,
) -> Tile:
    if client is not None and isinstance(client, OholProtocolClient):
        step = client._resolve_move_step(start, target)
        if step is not None:
            return step
    return step_toward(start, target)


def serialize_action(action: Action, client: OholProtocolProbe | None = None) -> str:
    if action.type is ActionType.SAY:
        return f"SAY 0 0 {action.payload['text']}#"
    if action.type is ActionType.MOVE_TO:
        start = client._action_tile if client is not None else Tile(
            action.payload.get("start_x", 0),
            action.payload.get("start_y", 0),
        )
        target = Tile(action.payload["x"], action.payload["y"])
        step = _resolve_move_step(start, target, client)
        sequence = action.payload.get("sequence")
        if sequence is None:
            sequence = (client.move_sequence + 1) if client is not None else 1
        dx = step.x - start.x
        dy = step.y - start.y
        if client is not None:
            client.move_sequence = int(sequence)
        return f"MOVE {start.x} {start.y} @{sequence} {dx} {dy}#"
    if action.type is ActionType.FORCE:
        return f"FORCE {action.payload['x']} {action.payload['y']}#"
    if action.type is ActionType.PICK_UP:
        return f"USE {action.payload['x']} {action.payload['y']}#"
    if action.type is ActionType.DROP:
        slot = action.payload.get("slot", -1)
        return f"DROP {action.payload['x']} {action.payload['y']} {slot}#"
    if action.type is ActionType.USE:
        return f"USE {action.payload['target_x']} {action.payload['target_y']}#"
    if action.type is ActionType.USE_SELF:
        if client is not None:
            tile = client._action_tile
        else:
            tile = Tile(action.payload["x"], action.payload["y"])
        return f"SELF {tile.x} {tile.y} -1#"
    if action.type is ActionType.WAIT:
        return f"WAIT {action.payload.get('ticks', 1)}#"
    raise ValueError(f"Unsupported action type: {action.type}")
