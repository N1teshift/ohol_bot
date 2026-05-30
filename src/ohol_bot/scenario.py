from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import ObjectState, Observation, PlayerState, Tile


def load_scenario(path: str | Path) -> list[Observation]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    observations = data.get("observations", [])
    if not observations:
        raise ValueError(f"Scenario has no observations: {path}")
    return [_parse_observation(item) for item in observations]


def _parse_observation(data: dict[str, Any]) -> Observation:
    player = data["self"]
    return Observation(
        tick=int(data["tick"]),
        self=PlayerState(
            player_id=int(player["player_id"]),
            tile=_parse_tile(player["tile"]),
            age=float(player["age"]),
            food_store=int(player["food_store"]),
            max_food_store=int(player["max_food_store"]),
            held_object_id=player.get("held_object_id"),
            mother_id=player.get("mother_id"),
            lineage_id=player.get("lineage_id"),
        ),
        nearby_objects=tuple(_parse_object(obj) for obj in data.get("nearby_objects", [])),
        nearby_players=tuple(),
        home=_parse_tile(data["home"]) if data.get("home") else None,
        facts=dict(data.get("facts", {})),
    )


def _parse_tile(data: dict[str, Any]) -> Tile:
    return Tile(x=int(data["x"]), y=int(data["y"]))


def _parse_object(data: dict[str, Any]) -> ObjectState:
    return ObjectState(
        object_id=int(data["object_id"]),
        name=str(data["name"]),
        tile=_parse_tile(data["tile"]),
        food_value=int(data.get("food_value", 0)),
        portable=bool(data.get("portable", True)),
    )
