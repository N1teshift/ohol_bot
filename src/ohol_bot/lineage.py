from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from .game_data import OholGameData, race_name_for_id
from .model import PlayerState
from .protocol_messages import LineageEntry

PlayerLineage = LineageEntry


def apply_lineage_entries(
    lineages: dict[int, PlayerLineage],
    entries: tuple[LineageEntry, ...],
) -> None:
    for entry in entries:
        lineages[entry.player_id] = entry


def enrich_player_with_lineage(
    player: PlayerState,
    lineages: Mapping[int, PlayerLineage],
    *,
    game_data: OholGameData | None = None,
) -> PlayerState:
    lineage = lineages.get(player.player_id)
    if lineage is None:
        return _enrich_player_race(player, game_data)

    mother_id = lineage.ancestor_ids[0] if lineage.ancestor_ids else None
    enriched = replace(
        player,
        mother_id=mother_id,
        lineage_id=lineage.lineage_eve_id,
        ancestor_ids=lineage.ancestor_ids,
    )
    return _enrich_player_race(enriched, game_data)


def _enrich_player_race(
    player: PlayerState,
    game_data: OholGameData | None,
) -> PlayerState:
    if game_data is None or player.display_id is None:
        return player
    obj = game_data.objects.get(player.display_id)
    if obj is None or obj.race <= 0:
        return player
    race_name = race_name_for_id(obj.race)
    return replace(player, race_id=obj.race, race_name=race_name)
