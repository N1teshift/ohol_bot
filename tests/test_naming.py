from ohol_bot.model import PlayerState, Tile
from ohol_bot.naming import (
    PlayerIdentity,
    apply_naming_from_speech,
    extract_name_after_phrase,
    DEFAULT_BABY_NAMING_PHRASES,
    DEFAULT_FAMILY_NAMING_PHRASES,
)


def _player(
    player_id: int,
    x: int,
    y: int,
    *,
    age: float = 20.0,
    held_baby_id: int | None = None,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        tile=Tile(x, y),
        age=age,
        food_store=20,
        max_food_store=20,
        held_baby_id=held_baby_id,
    )


def test_extract_family_name_from_my_name_is() -> None:
    assert (
        extract_name_after_phrase("MY NAME IS DOE", DEFAULT_FAMILY_NAMING_PHRASES)
        == "DOE"
    )


def test_extract_baby_name_from_your_name_is() -> None:
    assert (
        extract_name_after_phrase("YOUR NAME IS TOM", DEFAULT_BABY_NAMING_PHRASES)
        == "TOM"
    )


def test_eve_self_names_with_my_name_is() -> None:
    identities: dict[int, PlayerIdentity] = {}
    eve_players: set[int] = set()
    players = {5: _player(5, 0, 0, age=18.0)}

    event = apply_naming_from_speech(
        speaker_id=5,
        text="MY NAME IS DOE",
        players=players,
        identities=identities,
        eve_players=eve_players,
    )

    assert event is not None
    assert event.kind == "eve_family"
    assert identities[5].display_name == "EVE DOE"
    assert 5 in eve_players


def test_mother_names_held_baby() -> None:
    identities = {8: PlayerIdentity(first_name="EVE", family_name="DOE", is_eve=True)}
    eve_players = {8}
    players = {
        8: _player(8, 0, 0, age=25.0, held_baby_id=9),
        9: _player(9, 0, 0, age=0.5),
    }

    event = apply_naming_from_speech(
        speaker_id=8,
        text="YOUR NAME IS TOM",
        players=players,
        identities=identities,
        eve_players=eve_players,
    )

    assert event is not None
    assert event.kind == "baby"
    assert event.target_id == 9
    assert identities[9].display_name == "TOM DOE"


def test_nearby_eve_gets_family_name_from_your_name_is() -> None:
    identities: dict[int, PlayerIdentity] = {}
    eve_players: set[int] = set()
    players = {
        8: _player(8, 0, 0, age=25.0),
        9: _player(9, 1, 0, age=18.0),
    }

    event = apply_naming_from_speech(
        speaker_id=8,
        text="YOUR NAME IS SMITH",
        players=players,
        identities=identities,
        eve_players=eve_players,
    )

    assert event is not None
    assert event.kind == "eve_family"
    assert identities[9].display_name == "EVE SMITH"


def test_nearby_child_gets_first_name_from_your_name_is() -> None:
    identities = {8: PlayerIdentity(first_name="EVE", family_name="DOE", is_eve=True)}
    eve_players = {8}
    players = {
        8: _player(8, 0, 0, age=25.0),
        9: _player(9, 1, 0, age=6.0),
    }

    event = apply_naming_from_speech(
        speaker_id=8,
        text="YOUR NAME IS TOM",
        players=players,
        identities=identities,
        eve_players=eve_players,
    )

    assert event is not None
    assert event.kind == "baby"
    assert identities[9].display_name == "TOM DOE"
