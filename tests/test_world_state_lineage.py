from ohol_bot.biomes import BiomeCatalog
from ohol_bot.game_data import OholGameData, OholObject
from ohol_bot.model import PlayerState, Tile
from ohol_bot.protocol_client import OholProtocolClient
from ohol_bot.protocol_messages import (
    LineageMessage,
    PlayerUpdateMessage,
    ProtocolMessageType,
    parse_protocol_message,
)
from ohol_bot.world_state import WorldState


def _game_data() -> OholGameData:
    return OholGameData(
        objects={
            100: OholObject(100, "Man", male=True, race=3),
            101: OholObject(101, "Woman", male=False, race=2),
        },
        transitions=(),
        biomes=BiomeCatalog(names={0: "Grasslands"}),
    )


def test_world_state_applies_lineage_to_observation() -> None:
    state = WorldState()
    state.self_player_id = 14
    state.players[14] = PlayerState(
        player_id=14,
        tile=Tile(0, 0),
        age=1.0,
        food_store=4,
        max_food_store=4,
        display_id=101,
    )
    state.players[13] = PlayerState(
        player_id=13,
        tile=Tile(1, 0),
        age=25.0,
        food_store=20,
        max_food_store=20,
        display_id=101,
    )
    state.apply(parse_protocol_message("LN\n13 eve=13\n14 13 eve=13"))

    observation = state.to_observation(game_data=_game_data())

    assert observation.self.mother_id == 13
    assert observation.self.lineage_id == 13
    assert observation.self.ancestor_ids == (13,)
    assert observation.self.race_name == "Asian"
    assert observation.facts["self_mother_id"] == 13
    assert observation.facts["self_lineage_eve_id"] == 13
    assert observation.facts["self_ancestor_ids"] == (13,)

    mother = next(p for p in observation.nearby_players if p.player_id == 13)
    assert mother.relation_to_self == "your mother"
    assert observation.facts["nearby_relations"] == {13: "your mother"}


def test_world_state_sister_relation() -> None:
    state = WorldState()
    state.self_player_id = 14
    state.self_age_base = 20.0
    state.players[14] = PlayerState(
        player_id=14,
        tile=Tile(0, 0),
        age=20.0,
        food_store=20,
        max_food_store=20,
        display_id=101,
    )
    state.players[15] = PlayerState(
        player_id=15,
        tile=Tile(2, 0),
        age=20.0,
        food_store=20,
        max_food_store=20,
        display_id=100,
    )
    state.apply(parse_protocol_message("LN\n14 50 eve=50\n15 50 eve=50"))
    game_data = _game_data()

    observation = state.to_observation(game_data=game_data)
    sister = next(p for p in observation.nearby_players if p.player_id == 15)

    assert sister.relation_to_self == "your twin brother"


def test_lineage_does_not_change_self_player_id_in_client() -> None:
    client = OholProtocolClient()
    client._dispatch_message(
        parse_protocol_message("PU\n13 0 0 0 0 0 0 0 0 0 0 0 0 0 10 20 18.0 15.0 4.0")
    )
    client._dispatch_message(parse_protocol_message("LN\n13 eve=13\n14 13 eve=13"))

    assert client.self_player_id == 13
    assert client.world_state.player_lineages[14].ancestor_ids == (13,)
