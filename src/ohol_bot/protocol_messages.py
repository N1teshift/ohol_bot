from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from enum import Enum

from .model import ObjectState, Observation, PlayerState, Tile


class ProtocolMessageType(str, Enum):
    SERVER_LOGIN = "SN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FRAME = "FM"
    PLAYER_UPDATE = "PU"
    PLAYER_MOVEMENT = "PM"
    PLAYER_SAYS = "PS"
    COMPRESSED = "CM"
    MAP_CHUNK = "MC"
    MAP_CHANGE = "MX"
    FOOD_CHANGE = "FX"
    CRAVING = "CR"
    LINEAGE = "LN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    type: ProtocolMessageType
    raw: str


@dataclass(frozen=True, slots=True)
class ServerLoginMessage(ProtocolMessage):
    player_count: int | None = None
    challenge: str | None = None
    version: int | None = None


@dataclass(frozen=True, slots=True)
class PlayerUpdateEntry:
    player_id: int
    display_id: int | None = None
    x: int | None = None
    y: int | None = None
    age: float | None = None
    inv_age_rate_seconds_per_year: float | None = None
    held_object_id: int | None = None
    held_baby_id: int | None = None
    held_yum: bool = False
    just_ate: bool = False
    done_moving_seq: int = 0
    force_position: bool = False
    holding_field_present: bool = False
    raw_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayerMovementEntry:
    player_id: int
    x: int | None = None
    y: int | None = None
    raw_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayerUpdateMessage(ProtocolMessage):
    players: tuple[PlayerUpdateEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayerMovementMessage(ProtocolMessage):
    players: tuple[PlayerMovementEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayerSaysMessage(ProtocolMessage):
    player_id: int | None = None
    text: str = ""
    raw_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompressedMessage(ProtocolMessage):
    decompressed: tuple[ProtocolMessage, ...] = ()


@dataclass(frozen=True, slots=True)
class MapChunkMessage(ProtocolMessage):
    size_x: int | None = None
    size_y: int | None = None
    base_x: int | None = None
    base_y: int | None = None
    binary_size: int | None = None
    compressed_size: int | None = None
    cells: tuple["MapChunkCell", ...] = ()


@dataclass(frozen=True, slots=True)
class MapChunkCell:
    x: int
    y: int
    biome_id: int
    floor_id: int
    object_id: int


@dataclass(frozen=True, slots=True)
class MapTileChange:
    x: int
    y: int
    object_id: int
    floor_id: int | None = None


@dataclass(frozen=True, slots=True)
class MapChangeMessage(ProtocolMessage):
    changes: tuple[MapTileChange, ...] = ()


@dataclass(frozen=True, slots=True)
class FoodChangeMessage(ProtocolMessage):
    food_store: int = 0
    food_capacity: int = 1
    last_ate_id: int | None = None
    last_ate_fill_max: int | None = None
    last_speed: float | None = None
    responsible_player_id: int | None = None
    yum_bonus: int = 0
    yum_multiplier: int = 0


@dataclass(frozen=True, slots=True)
class CravingMessage(ProtocolMessage):
    food_id: int | None = None
    yum_bonus: int = 0


@dataclass(frozen=True, slots=True)
class LineageMessage(ProtocolMessage):
    player_id: int | None = None


def split_frames(buffer: bytes) -> tuple[str, ...]:
    text = buffer.decode("utf-8", errors="replace")
    return tuple(part for part in text.split("#") if part.strip())


def parse_protocol_buffer(buffer: bytes) -> tuple[ProtocolMessage, ...]:
    return tuple(parse_protocol_message(frame) for frame in split_frames(buffer))


def parse_protocol_message(frame: str) -> ProtocolMessage:
    normalized = frame.strip()
    if not normalized:
        return ProtocolMessage(ProtocolMessageType.UNKNOWN, frame)

    head = normalized.split(maxsplit=1)[0]
    if head == "SN":
        return _parse_server_login(normalized)
    if head == "ACCEPTED":
        return ProtocolMessage(ProtocolMessageType.ACCEPTED, normalized)
    if head.startswith("REJECTED") or head == "NO_LIFE_TOKENS":
        return ProtocolMessage(ProtocolMessageType.REJECTED, normalized)
    if head == "FM":
        return ProtocolMessage(ProtocolMessageType.FRAME, normalized)
    if head == "PU":
        return _parse_player_update(normalized)
    if head == "PM":
        return _parse_player_movement(normalized)
    if head == "PS":
        return _parse_player_says(normalized)
    if head == "CM":
        return _parse_compressed(normalized)
    if head == "MC":
        return _parse_map_chunk(normalized)
    if head == "MX":
        return _parse_map_change(normalized)
    if head == "FX":
        return _parse_food_change(normalized)
    if head == "CR":
        return _parse_craving(normalized)
    if head == "LN":
        return _parse_lineage(normalized)
    return ProtocolMessage(ProtocolMessageType.UNKNOWN, normalized)


def observation_from_messages(messages: tuple[ProtocolMessage, ...]) -> Observation:
    latest_player: PlayerUpdateEntry | PlayerMovementEntry | None = None
    nearby_objects: list[ObjectState] = []
    facts: dict[str, object] = {"message_count": len(messages)}

    for message in _flatten_messages(messages):
        if isinstance(message, PlayerUpdateMessage) and message.players:
            latest_player = message.players[-1]
        elif isinstance(message, PlayerMovementMessage) and message.players:
            latest_player = message.players[-1]
        elif isinstance(message, MapChunkMessage):
            facts["last_map_chunk"] = {
                "base_x": message.base_x,
                "base_y": message.base_y,
                "cells": len(message.cells),
            }

    tile = Tile(latest_player.x or 0, latest_player.y or 0) if latest_player else Tile(0, 0)
    player_id = latest_player.player_id if latest_player else -1
    held = latest_player.held_object_id if isinstance(latest_player, PlayerUpdateEntry) else None
    return Observation(
        tick=0,
        self=PlayerState(
            player_id=player_id,
            tile=tile,
            age=0,
            food_store=1,
            max_food_store=1,
            held_object_id=held,
        ),
        nearby_objects=tuple(nearby_objects),
        facts=facts,
    )


def _parse_server_login(raw: str) -> ServerLoginMessage:
    fields = raw.split()
    return ServerLoginMessage(
        type=ProtocolMessageType.SERVER_LOGIN,
        raw=raw,
        player_count=_int_at(fields, 1),
        challenge=fields[2] if len(fields) > 2 else None,
        version=_int_at(fields, 3),
    )


def _parse_player_update(raw: str) -> PlayerUpdateMessage:
    entries = []
    for line in raw.splitlines()[1:]:
        fields = tuple(field for field in line.split() if field)
        if not fields:
            continue
        held_object_id, held_baby_id = (
            _parse_holding(fields[6]) if len(fields) > 6 else (None, None)
        )
        holding_field_present = len(fields) > 6
        done_moving_seq = _safe_int(fields[12], 0) or 0 if len(fields) > 12 else 0
        force_position = (_safe_int(fields[13], 0) or 0) > 0 if len(fields) > 13 else False
        held_yum = _safe_int(fields[24], 0) == 1 if len(fields) > 24 else False
        just_ate = _safe_int(fields[20], 0) == 1 if len(fields) > 20 else False
        entries.append(
            PlayerUpdateEntry(
                player_id=_safe_int(fields[0], -1),
                display_id=_safe_int(fields[1], None) if len(fields) > 1 else None,
                held_object_id=held_object_id,
                held_baby_id=held_baby_id,
                held_yum=held_yum,
                just_ate=just_ate,
                done_moving_seq=done_moving_seq,
                force_position=force_position,
                holding_field_present=holding_field_present,
                x=_safe_int(fields[14], None) if len(fields) > 14 else None,
                y=_safe_int(fields[15], None) if len(fields) > 15 else None,
                age=_safe_float(fields[16], None) if len(fields) > 16 else None,
                inv_age_rate_seconds_per_year=(
                    _safe_float(fields[17], None) if len(fields) > 17 else None
                ),
                raw_fields=fields,
            )
        )
    return PlayerUpdateMessage(ProtocolMessageType.PLAYER_UPDATE, raw, tuple(entries))


def _parse_player_movement(raw: str) -> PlayerMovementMessage:
    entries = []
    for line in raw.splitlines()[1:]:
        fields = tuple(field for field in line.split() if field)
        if len(fields) < 3:
            continue
        start_x = _safe_int(fields[1], 0) or 0
        start_y = _safe_int(fields[2], 0) or 0
        x, y = start_x, start_y
        if len(fields) >= 8:
            for index in range(6, len(fields) - 1, 2):
                offset_x = _safe_int(fields[index], 0) or 0
                offset_y = _safe_int(fields[index + 1], 0) or 0
                x = start_x + offset_x
                y = start_y + offset_y
        entries.append(
            PlayerMovementEntry(
                player_id=_safe_int(fields[0], -1),
                x=x,
                y=y,
                raw_fields=fields,
            )
        )
    return PlayerMovementMessage(ProtocolMessageType.PLAYER_MOVEMENT, raw, tuple(entries))


def _parse_player_says(raw: str) -> PlayerSaysMessage:
    lines = raw.splitlines()
    payload = lines[1].strip() if len(lines) > 1 else raw.split(maxsplit=1)[1] if " " in raw else ""
    fields = tuple(field for field in payload.split() if field)
    player_id = _safe_int(fields[0], None) if fields else None
    text_fields = fields[1:] if player_id is not None else fields
    if len(text_fields) >= 3 and _safe_int(text_fields[0], None) is not None and _safe_int(text_fields[1], None) is not None:
        text_fields = text_fields[2:]
    return PlayerSaysMessage(
        ProtocolMessageType.PLAYER_SAYS,
        raw,
        player_id=player_id,
        text=" ".join(text_fields).strip(),
        raw_fields=fields,
    )


def _parse_compressed(raw: str) -> CompressedMessage:
    parts = raw.split("#", maxsplit=1)
    if len(parts) != 2:
        return CompressedMessage(ProtocolMessageType.COMPRESSED, raw)
    try:
        payload = bytes.fromhex(parts[1])
        decompressed = zlib.decompress(payload)
    except (ValueError, zlib.error):
        return CompressedMessage(ProtocolMessageType.COMPRESSED, raw)
    return CompressedMessage(
        ProtocolMessageType.COMPRESSED,
        raw,
        parse_protocol_buffer(decompressed),
    )


def _parse_map_change(raw: str) -> MapChangeMessage:
    changes: list[MapTileChange] = []
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        object_id = _safe_int(fields[3], 0) or 0
        changes.append(
            MapTileChange(
                x=_safe_int(fields[0], 0) or 0,
                y=_safe_int(fields[1], 0) or 0,
                floor_id=_safe_int(fields[2], None),
                object_id=object_id,
            )
        )
    return MapChangeMessage(ProtocolMessageType.MAP_CHANGE, raw, tuple(changes))


def _parse_food_change(raw: str) -> FoodChangeMessage:
    fields = raw.split()
    return FoodChangeMessage(
        type=ProtocolMessageType.FOOD_CHANGE,
        raw=raw,
        food_store=_safe_int(fields[1], 0) if len(fields) > 1 else 0,
        food_capacity=max(_safe_int(fields[2], 1) if len(fields) > 2 else 1, 1),
        last_ate_id=_safe_int(fields[3], None) if len(fields) > 3 else None,
        last_ate_fill_max=_safe_int(fields[4], None) if len(fields) > 4 else None,
        last_speed=_safe_float(fields[5], None) if len(fields) > 5 else None,
        responsible_player_id=_safe_int(fields[6], None) if len(fields) > 6 else None,
        yum_bonus=_safe_int(fields[7], 0) if len(fields) > 7 else 0,
        yum_multiplier=_safe_int(fields[8], 0) if len(fields) > 8 else 0,
    )


def _parse_craving(raw: str) -> CravingMessage:
    fields = raw.split()
    food_id = _safe_int(fields[1], None) if len(fields) > 1 else None
    yum_bonus = _safe_int(fields[2], 0) if len(fields) > 2 else 0
    if food_id is not None and food_id < 0:
        food_id = None
    return CravingMessage(
        type=ProtocolMessageType.CRAVING,
        raw=raw,
        food_id=food_id,
        yum_bonus=yum_bonus or 0,
    )


def _parse_lineage(raw: str) -> LineageMessage:
    player_id = None
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if fields:
            player_id = _safe_int(fields[0], player_id)
    return LineageMessage(ProtocolMessageType.LINEAGE, raw, player_id=player_id)


def _parse_map_chunk(raw: str) -> MapChunkMessage:
    if "\n__PAYLOAD__\n" in raw:
        header, payload = raw.split("\n__PAYLOAD__\n", 1)
        message = _parse_map_chunk_header(header)
        return _attach_map_chunk_payload(message, payload)

    return _parse_map_chunk_header(raw)


def _parse_map_chunk_header(raw: str) -> MapChunkMessage:
    numbers = [int(value) for value in re.findall(r"-?\d+", raw)]
    if len(numbers) < 6:
        return MapChunkMessage(type=ProtocolMessageType.MAP_CHUNK, raw=raw)
    return MapChunkMessage(
        type=ProtocolMessageType.MAP_CHUNK,
        raw=raw,
        size_x=numbers[0],
        size_y=numbers[1],
        base_x=numbers[2],
        base_y=numbers[3],
        binary_size=numbers[4],
        compressed_size=numbers[5],
    )


def _attach_map_chunk_payload(message: MapChunkMessage, payload: str) -> MapChunkMessage:
    if message.size_x is None or message.size_y is None:
        return message
    if message.base_x is None or message.base_y is None:
        return message

    tokens = payload.split()
    cells: list[MapChunkCell] = []
    for index, token in enumerate(tokens):
        parts = token.split(":")
        if len(parts) < 3:
            continue
        biome_id = _safe_int(parts[0], 0) or 0
        floor_id = _safe_int(parts[1], 0) or 0
        object_id = _safe_int(parts[2], 0) or 0
        cell_x = message.base_x + (index % message.size_x)
        cell_y = message.base_y + (index // message.size_x)
        cells.append(
            MapChunkCell(
                x=cell_x,
                y=cell_y,
                biome_id=biome_id,
                floor_id=floor_id,
                object_id=object_id,
            )
        )

    return MapChunkMessage(
        type=message.type,
        raw=message.raw,
        size_x=message.size_x,
        size_y=message.size_y,
        base_x=message.base_x,
        base_y=message.base_y,
        binary_size=message.binary_size,
        compressed_size=message.compressed_size,
        cells=tuple(cells),
    )


def _flatten_messages(messages: tuple[ProtocolMessage, ...]) -> tuple[ProtocolMessage, ...]:
    flattened: list[ProtocolMessage] = []
    for message in messages:
        flattened.append(message)
        if isinstance(message, CompressedMessage):
            flattened.extend(_flatten_messages(message.decompressed))
    return tuple(flattened)


def _int_at(fields: list[str], index: int) -> int | None:
    if len(fields) <= index:
        return None
    return _safe_int(fields[index], None)


def _safe_int(value: str, default: int | None) -> int | None:
    try:
        return int(value)
    except ValueError:
        return default


def _safe_float(value: str, default: float | None) -> float | None:
    try:
        return float(value)
    except ValueError:
        return default


def _parse_holding(token: str) -> tuple[int | None, int | None]:
    if not token:
        return None, None
    head = token.split(",", maxsplit=1)[0]
    try:
        held_id = int(head)
    except ValueError:
        return None, None
    if held_id < 0:
        return None, -held_id
    if held_id > 0:
        return held_id, None
    return None, None
