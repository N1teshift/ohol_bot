from ohol_bot.model import Action, ActionType, Observation, PlayerState, Tile
from ohol_bot.protocol_client import OholProtocolClient, _batch_has_frame
from ohol_bot.protocol_messages import (
    CompressedMessage,
    ProtocolMessage,
    ProtocolMessageType,
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
