from pathlib import Path

from ohol_bot.naming import apply_assigned_name_line, PlayerIdentity
from ohol_bot.ohol_names import NameCatalog, parse_assigned_name_line

RUNTIME = Path(__file__).resolve().parents[1] / ".ohol_runtime" / "server"


def test_parse_assigned_name_line() -> None:
    assert parse_assigned_name_line("136 ROCKELL CARROTHERS") == (
        136,
        "ROCKELL",
        "CARROTHERS",
    )


def test_ingest_assigned_name_line_overrides_speech_guess() -> None:
    identities: dict[int, PlayerIdentity] = {136: PlayerIdentity(first_name="ROCK")}
    eve_players: set[int] = set()

    apply_assigned_name_line("136 ROCKELL CARROTHERS", identities, eve_players)

    assert identities[136].display_name == "ROCKELL CARROTHERS"


def test_catalog_maps_rock_to_rockell_for_female_names() -> None:
    if not (RUNTIME / "femaleNames.txt").exists():
        return
    catalog = NameCatalog.load(RUNTIME)
    assert catalog.close_first_name("ROCK", female=True) == "ROCKELL"


def test_you_are_rock_uses_prescribed_name_from_server_log() -> None:
    identities: dict[int, PlayerIdentity] = {136: PlayerIdentity(first_name="ROCK")}
    eve_players: set[int] = set()

    apply_assigned_name_line("136 ROCKELL CARROTHERS", identities, eve_players)

    assert identities[136].display_name == "ROCKELL CARROTHERS"
