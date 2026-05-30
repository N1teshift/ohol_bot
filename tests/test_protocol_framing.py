import zlib

from ohol_bot.protocol_framing import ProtocolFrameReader
from ohol_bot.protocol_messages import MapChunkMessage, ProtocolMessageType, parse_protocol_message


def test_frame_reader_handles_split_accepted_frame() -> None:
    reader = ProtocolFrameReader()
    frames = reader.ingest(b"SN 0 challenge 437#ACCEPT")
    assert frames == ("SN 0 challenge 437",)
    frames = reader.ingest(b"ED#FM#")
    assert frames == ("ACCEPTED", "FM")


def test_frame_reader_decompresses_cm_payload() -> None:
    inner = b"PU\n5 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2 18.0 15.0 4.0#FM#"
    compressed = zlib.compress(inner)
    reader = ProtocolFrameReader()
    header = f"CM\n{len(inner)} {len(compressed)}"
    frames = reader.ingest(f"{header}#".encode("utf-8") + compressed)
    assert len(frames) == 2
    assert frames[0].startswith("PU\n")


def test_parse_map_chunk_payload_cells() -> None:
    payload = "0:10:0 0:11:100 2:12:0"
    frame = f"MC\n2 1 10 20\n{len(payload)} {len(payload)}\n__PAYLOAD__\n{payload}"
    message = parse_protocol_message(frame)

    assert isinstance(message, MapChunkMessage)
    assert message.type is ProtocolMessageType.MAP_CHUNK
    assert len(message.cells) == 3
    assert message.cells[0].biome_id == 0
    assert message.cells[0].floor_id == 10
    assert message.cells[1].object_id == 100
    assert message.cells[1].biome_id == 0
    assert message.cells[1].floor_id == 11
    assert message.cells[1].x == 11
    assert message.cells[1].y == 20
    assert message.cells[2].biome_id == 2
