from __future__ import annotations

import re
import zlib
from dataclasses import dataclass

from .protocol_messages import parse_protocol_message


@dataclass(frozen=True, slots=True)
class PendingBinaryPayload:
    kind: str
    compressed_size: int
    decompressed_size: int
    header_text: str


@dataclass
class ProtocolFrameReader:
    """Split OHOL socket bytes into complete text protocol frames."""

    buffer: bytes = b""
    pending: PendingBinaryPayload | None = None

    def ingest(self, data: bytes) -> tuple[str, ...]:
        if not data:
            return ()
        self.buffer += data
        frames: list[str] = []

        while True:
            if self.pending is not None:
                if len(self.buffer) < self.pending.compressed_size:
                    break
                compressed = self.buffer[: self.pending.compressed_size]
                self.buffer = self.buffer[self.pending.compressed_size :]
                pending = self.pending
                self.pending = None

                try:
                    decompressed = zlib.decompress(compressed)
                except zlib.error:
                    continue

                if pending.kind == "cm":
                    text = decompressed[: pending.decompressed_size].decode(
                        "utf-8", errors="replace"
                    )
                    frames.extend(_split_text_frames(text))
                elif pending.kind == "mc":
                    frames.append(
                        _combine_map_chunk(pending.header_text, decompressed[: pending.decompressed_size])
                    )
                continue

            index = self.buffer.find(b"#")
            if index == -1:
                break

            frame_bytes = self.buffer[:index]
            self.buffer = self.buffer[index + 1 :]
            if not frame_bytes.strip():
                continue

            frame_text = frame_bytes.decode("utf-8", errors="replace")
            pending = _pending_from_frame(frame_text)
            if pending is not None:
                self.pending = pending
                continue

            frames.append(frame_text)

        return tuple(frames)


def _split_text_frames(text: str) -> tuple[str, ...]:
    return tuple(part for part in text.split("#") if part.strip())


def _pending_from_frame(frame_text: str) -> PendingBinaryPayload | None:
    if frame_text.startswith("CM\n"):
        match = re.match(r"CM\n(\d+)\s+(\d+)", frame_text)
        if match is None:
            return None
        return PendingBinaryPayload(
            kind="cm",
            decompressed_size=int(match.group(1)),
            compressed_size=int(match.group(2)),
            header_text=frame_text,
        )

    if frame_text.startswith("MC\n"):
        numbers = [int(value) for value in re.findall(r"-?\d+", frame_text)]
        if len(numbers) < 6:
            return None
        return PendingBinaryPayload(
            kind="mc",
            decompressed_size=numbers[4],
            compressed_size=numbers[5],
            header_text=frame_text,
        )

    return None


def _combine_map_chunk(header_text: str, decompressed: bytes) -> str:
    payload = decompressed.decode("utf-8", errors="replace")
    return f"{header_text}\n__PAYLOAD__\n{payload}"
