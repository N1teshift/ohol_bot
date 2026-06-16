from ohol_bot.model import Action, ActionType, Observation, PlayerState, Tile
from ohol_bot.protocol_client import OholProtocolClient, _batch_has_frame
from ohol_bot.protocol_messages import (
    CompressedMessage,
    ProtocolMessage,
    ProtocolMessageType,
    parse_protocol_message,
)
from ohol_bot.runner import run_live_episode
from ohol_bot.movement_policy import MovementFollowPolicy


def test_batch_has_frame_detects_top_level_fm() -> None:
    messages = (ProtocolMessage(ProtocolMessageType.FRAME, "FM"),)

    assert _batch_has_frame(messages) is True


def test_batch_has_frame_detects_fm_inside_compressed_batch() -> None:
    messages = (
        CompressedMessage(
            ProtocolMessageType.COMPRESSED,
            "CM\n0 0",
            (ProtocolMessage(ProtocolMessageType.FRAME, "FM"),),
        ),
    )

    assert _batch_has_frame(messages) is True


def test_batch_has_frame_false_for_player_update_only() -> None:
    from ohol_bot.protocol_messages import parse_protocol_message

    messages = (
        parse_protocol_message("PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0"),
    )

    assert _batch_has_frame(messages) is False


def test_wait_for_frame_advances_world_tick() -> None:
    import time

    from ohol_bot.model import PlayerState, Tile

    client = OholProtocolClient()
    client.keep_alive_interval_seconds = 9999.0
    client._last_keep_alive_at = time.monotonic()
    client.world_state.self_player_id = 5
    client.world_state.players[5] = PlayerState(
        player_id=5,
        tile=Tile(0, 0),
        age=18.0,
        food_store=10,
        max_food_store=20,
    )
    reads = iter([b"FM#", b""])

    def fake_try_read(max_bytes: int = 4096) -> bytes:
        data = next(reads, b"")
        if data:
            client.received_messages.append(data)
            client._ingest_bytes(data)
        return data

    client.try_read = fake_try_read  # type: ignore[method-assign]

    assert client.world_state.tick == 0
    assert client.wait_for_frame(timeout_seconds=1.0) is True
    assert client.world_state.tick == 1


def test_wait_for_frame_increments_server_frames() -> None:
    import time

    client = OholProtocolClient()
    client.keep_alive_interval_seconds = 9999.0
    client._last_keep_alive_at = time.monotonic()
    reads = iter([b"FM#", b""])

    def fake_try_read(max_bytes: int = 4096) -> bytes:
        data = next(reads, b"")
        if data:
            client.received_messages.append(data)
            client._ingest_bytes(data)
        return data

    client.try_read = fake_try_read  # type: ignore[method-assign]

    assert client.wait_for_frame(timeout_seconds=1.0) is True
    assert client.server_frames == 1


def test_frame_paced_runner_waits_per_frame_not_tick_seconds() -> None:
    class FramePacedStub(OholProtocolClient):
        def __init__(self) -> None:
            super().__init__()
            self.logged_in = True
            self.frame_waits = 0
            self.poll_until_calls = 0
            self._observations = [
                Observation(
                    tick=1,
                    self=PlayerState(
                        player_id=1,
                        tile=Tile(0, 0),
                        age=18,
                        food_store=10,
                        max_food_store=20,
                    ),
                ),
                Observation(
                    tick=2,
                    self=PlayerState(
                        player_id=1,
                        tile=Tile(0, 0),
                        age=18,
                        food_store=10,
                        max_food_store=20,
                    ),
                ),
            ]

        def login(self, timeout_seconds: float = 15.0) -> None:
            return

        def wait_for_frame(self, timeout_seconds: float = 30.0) -> bool:
            self.frame_waits += 1
            return self.frame_waits <= len(self._observations)

        def poll_until(self, timeout_seconds: float = 1.0) -> None:
            self.poll_until_calls += 1

        def observe(self) -> Observation:
            return self._observations[min(self.frame_waits - 1, len(self._observations) - 1)]

        def send(self, action: Action) -> None:
            if action.type is not ActionType.WAIT:
                self._actions_sent += 1

        def close(self) -> None:
            return

    client = FramePacedStub()
    result = run_live_episode(
        client,
        MovementFollowPolicy(),
        max_ticks=2,
        frame_paced=True,
    )

    assert client.frame_waits == 2
    assert client.poll_until_calls == 0
    assert result.ticks == 2


def test_poll_for_window_counts_fm_frames() -> None:
    import time

    client = OholProtocolClient()
    client.keep_alive_interval_seconds = 9999.0
    client._last_keep_alive_at = time.monotonic()
    reads = iter([b"FM#", b"FM#", b""])

    def fake_try_read(max_bytes: int = 4096) -> bytes:
        data = next(reads, b"")
        if data:
            client.received_messages.append(data)
            client._ingest_bytes(data)
        return data

    client.try_read = fake_try_read  # type: ignore[method-assign]

    frames = client.poll_for_window(0.05)

    assert frames == 2
    assert client.server_frames == 2


def test_planner_hz_runner_uses_poll_window_not_wait_for_frame() -> None:
    class PlannerHzStub(OholProtocolClient):
        def __init__(self) -> None:
            super().__init__()
            self.logged_in = True
            self.poll_window_calls = 0
            self.frame_waits = 0
            self._observations = [
                Observation(
                    tick=1,
                    self=PlayerState(
                        player_id=1,
                        tile=Tile(0, 0),
                        age=18,
                        food_store=10,
                        max_food_store=20,
                    ),
                ),
                Observation(
                    tick=2,
                    self=PlayerState(
                        player_id=1,
                        tile=Tile(0, 0),
                        age=18,
                        food_store=10,
                        max_food_store=20,
                    ),
                ),
            ]

        def login(self, timeout_seconds: float = 15.0) -> None:
            return

        def poll_for_window(self, duration_seconds: float) -> int:
            self.poll_window_calls += 1
            return 1

        def wait_for_frame(self, timeout_seconds: float = 30.0) -> bool:
            self.frame_waits += 1
            return True

        def observe(self) -> Observation:
            index = min(self.poll_window_calls - 1, len(self._observations) - 1)
            return self._observations[index]

        def send(self, action: Action) -> None:
            if action.type is not ActionType.WAIT:
                self._actions_sent += 1

        def close(self) -> None:
            return

    client = PlannerHzStub()
    result = run_live_episode(
        client,
        MovementFollowPolicy(),
        max_ticks=2,
        frame_paced=True,
        planner_hz=6.0,
    )

    assert client.poll_window_calls == 2
    assert client.frame_waits == 0
    assert result.ticks == 2
