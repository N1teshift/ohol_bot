from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from .game_data import OholGameData
from .model import PlayerState, Tile
from .ohol_names import NameCatalog, parse_assigned_name_line

EVE_FIRST_NAME = "EVE"
NAMING_MAX_DISTANCE = 20.0
NEARBY_NAME_MIN_AGE = 5.0
EVE_NAMING_MIN_AGE = 15.0

# serverSettings/familyNamingPhrases.ini and babyNamingPhrases.ini (longest match first)
DEFAULT_FAMILY_NAMING_PHRASES: tuple[str, ...] = (
    "CALL ME EVE ",
    "I AM CALLED EVE ",
    "I AM NAMED EVE ",
    "MY NAME IS EVE ",
    "CALL ME ",
    "I AM EVE ",
    "I'M EVE ",
    "IM EVE ",
    "I AM CALLED ",
    "I AM NAMED ",
    "MY NAME IS ",
    "I AM ",
    "I'M ",
    "IM ",
)

DEFAULT_BABY_NAMING_PHRASES: tuple[str, ...] = (
    "YOU ARE CALLED ",
    "YOU ARE NAMED ",
    "YOUR NAME IS ",
    "I NAME YOU ",
    "I CALL YOU ",
    "YOU ARE ",
    "YOU'RE ",
    "YOURE ",
)


@dataclass(frozen=True, slots=True)
class PlayerIdentity:
    first_name: str | None = None
    family_name: str | None = None
    is_eve: bool = False

    @property
    def is_nameless(self) -> bool:
        return self.first_name is None and self.family_name is None

    @property
    def display_name(self) -> str | None:
        if self.first_name and self.family_name:
            return f"{self.first_name} {self.family_name}"
        if self.first_name:
            return self.first_name
        if self.family_name:
            return self.family_name
        return None


@dataclass(frozen=True, slots=True)
class NamingEvent:
    kind: str
    speaker_id: int
    target_id: int
    first_name: str | None
    family_name: str | None

    def as_fact(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "speaker_id": self.speaker_id,
            "target_id": self.target_id,
            "first_name": self.first_name,
            "family_name": self.family_name,
            "display_name": display_name(self.first_name, self.family_name),
        }


def display_name(
    first_name: str | None,
    family_name: str | None,
) -> str | None:
    identity = PlayerIdentity(first_name=first_name, family_name=family_name)
    return identity.display_name


def identity_display_name(identities: Mapping[int, PlayerIdentity], player_id: int) -> str | None:
    identity = identities.get(player_id)
    if identity is None:
        return None
    return identity.display_name


def load_phrases_from_ini(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    phrases: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        phrases.append(f"{line.upper()} ")
    phrases.sort(key=len, reverse=True)
    return tuple(phrases)


def load_naming_phrases(
    game_data_root: Path | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if game_data_root is None:
        return DEFAULT_FAMILY_NAMING_PHRASES, DEFAULT_BABY_NAMING_PHRASES
    settings = game_data_root / "serverSettings"
    family = load_phrases_from_ini(settings / "familyNamingPhrases.ini")
    baby = load_phrases_from_ini(settings / "babyNamingPhrases.ini")
    return (
        family or DEFAULT_FAMILY_NAMING_PHRASES,
        baby or DEFAULT_BABY_NAMING_PHRASES,
    )


def extract_name_after_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    normalized = " ".join(text.strip().upper().split())
    if not normalized:
        return None
    for phrase in phrases:
        if normalized.startswith(phrase):
            name = normalized[len(phrase) :].strip()
            if name:
                return name
    return None


def _chebyshev(a: Tile, b: Tile) -> float:
    return float(max(abs(a.x - b.x), abs(a.y - b.y)))


def _get_identity(
    identities: dict[int, PlayerIdentity],
    player_id: int,
) -> PlayerIdentity:
    return identities.get(player_id, PlayerIdentity())


def _is_nameless(identities: Mapping[int, PlayerIdentity], player_id: int) -> bool:
    return identities.get(player_id, PlayerIdentity()).is_nameless


def _closest_nameless_player(
    speaker_id: int,
    players: Mapping[int, PlayerState],
    identities: Mapping[int, PlayerIdentity],
    *,
    min_age: float,
    max_distance: float = NAMING_MAX_DISTANCE,
) -> int | None:
    speaker = players.get(speaker_id)
    if speaker is None:
        return None

    best_id: int | None = None
    best_distance = max_distance
    for player_id, player in players.items():
        if player_id == speaker_id:
            continue
        if not _is_nameless(identities, player_id):
            continue
        if player.age < min_age:
            continue
        distance = _chebyshev(speaker.tile, player.tile)
        if distance < best_distance:
            best_distance = distance
            best_id = player_id
    return best_id


def _normalize_name_token(name: str) -> str:
    return " ".join(name.strip().upper().split())


def player_is_female(player: PlayerState, game_data: OholGameData | None) -> bool:
    if player.display_id is None or game_data is None:
        return False
    obj = game_data.objects.get(player.display_id)
    if obj is None:
        return False
    return not obj.male


def _prescribe_first_name(
    raw_name: str,
    *,
    player: PlayerState | None,
    catalog: NameCatalog | None,
    game_data: OholGameData | None,
) -> str:
    normalized = _normalize_name_token(raw_name)
    if catalog is None or not catalog.available:
        return normalized
    female = player_is_female(player, game_data) if player is not None else False
    return catalog.close_first_name(normalized, female=female)


def _prescribe_family_name(raw_name: str, catalog: NameCatalog | None) -> str:
    normalized = _normalize_name_token(raw_name)
    if catalog is None or not catalog.available:
        return normalized
    return catalog.close_last_name(normalized)


def apply_assigned_name(
    player_id: int,
    first_name: str,
    family_name: str | None,
    identities: dict[int, PlayerIdentity],
    eve_players: set[int],
) -> None:
    first = _normalize_name_token(first_name)
    family = _normalize_name_token(family_name) if family_name else None
    is_eve = first == EVE_FIRST_NAME
    identities[player_id] = PlayerIdentity(
        first_name=first,
        family_name=family,
        is_eve=is_eve,
    )
    if is_eve:
        eve_players.add(player_id)


def apply_assigned_name_line(
    line: str,
    identities: dict[int, PlayerIdentity],
    eve_players: set[int],
) -> int | None:
    parsed = parse_assigned_name_line(line)
    if parsed is None:
        return None
    player_id, first_name, family_name = parsed
    apply_assigned_name(player_id, first_name, family_name, identities, eve_players)
    return player_id


def apply_eve_family_naming(
    target_id: int,
    family_name: str,
    identities: dict[int, PlayerIdentity],
    eve_players: set[int],
    *,
    catalog: NameCatalog | None = None,
) -> NamingEvent:
    family = _prescribe_family_name(family_name, catalog)
    identities[target_id] = PlayerIdentity(
        first_name=EVE_FIRST_NAME,
        family_name=family,
        is_eve=True,
    )
    eve_players.add(target_id)
    return NamingEvent(
        kind="eve_family",
        speaker_id=target_id,
        target_id=target_id,
        first_name=EVE_FIRST_NAME,
        family_name=family,
    )


def apply_baby_naming(
    speaker_id: int,
    target_id: int,
    first_name: str,
    identities: dict[int, PlayerIdentity],
    *,
    players: Mapping[int, PlayerState] | None = None,
    catalog: NameCatalog | None = None,
    game_data: OholGameData | None = None,
) -> NamingEvent:
    target_player = players.get(target_id) if players is not None else None
    first = _prescribe_first_name(
        first_name,
        player=target_player,
        catalog=catalog,
        game_data=game_data,
    )
    target = _get_identity(identities, target_id)
    namer = _get_identity(identities, speaker_id)
    family = target.family_name or namer.family_name
    identities[target_id] = PlayerIdentity(
        first_name=first,
        family_name=family,
        is_eve=target.is_eve,
    )
    return NamingEvent(
        kind="baby",
        speaker_id=speaker_id,
        target_id=target_id,
        first_name=first,
        family_name=family,
    )


def apply_naming_from_speech(
    *,
    speaker_id: int,
    text: str,
    players: Mapping[int, PlayerState],
    identities: dict[int, PlayerIdentity],
    eve_players: set[int],
    family_phrases: tuple[str, ...] = DEFAULT_FAMILY_NAMING_PHRASES,
    baby_phrases: tuple[str, ...] = DEFAULT_BABY_NAMING_PHRASES,
    catalog: NameCatalog | None = None,
    game_data: OholGameData | None = None,
) -> NamingEvent | None:
    if speaker_id is None:
        return None

    family_name = extract_name_after_phrase(text, family_phrases)
    if family_name is not None and _is_nameless(identities, speaker_id):
        return apply_eve_family_naming(
            speaker_id,
            family_name,
            identities,
            eve_players,
            catalog=catalog,
        )

    baby_name = extract_name_after_phrase(text, baby_phrases)
    if baby_name is None:
        return None

    speaker = players.get(speaker_id)
    if speaker is not None and speaker.held_baby_id is not None:
        baby_id = speaker.held_baby_id
        if _is_nameless(identities, baby_id):
            return apply_baby_naming(
                speaker_id,
                baby_id,
                baby_name,
                identities,
                players=players,
                catalog=catalog,
                game_data=game_data,
            )
        return None

    target_id = _closest_nameless_player(
        speaker_id,
        players,
        identities,
        min_age=NEARBY_NAME_MIN_AGE,
    )
    if target_id is None:
        return None

    target = players.get(target_id)
    if target is None:
        return None

    if target_id in eve_players or target.age >= EVE_NAMING_MIN_AGE:
        return apply_eve_family_naming(
            target_id,
            baby_name,
            identities,
            eve_players,
            catalog=catalog,
        )

    return apply_baby_naming(
        speaker_id,
        target_id,
        baby_name,
        identities,
        players=players,
        catalog=catalog,
        game_data=game_data,
    )


def enrich_player_with_identity(
    player: PlayerState,
    identities: Mapping[int, PlayerIdentity],
) -> PlayerState:
    identity = identities.get(player.player_id)
    if identity is None:
        return player
    return replace(
        player,
        first_name=identity.first_name,
        family_name=identity.family_name,
    )
