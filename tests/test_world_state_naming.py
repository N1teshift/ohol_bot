from ohol_bot.model import PlayerState, Tile
from ohol_bot.protocol_messages import PlayerSaysMessage, ProtocolMessageType
from ohol_bot.world_state import WorldState


def test_world_state_records_naming_from_chat() -> None:
    state = WorldState()
    state.self_player_id = 5
    state.players[5] = PlayerState(
        player_id=5,
        tile=Tile(0, 0),
        age=18.0,
        food_store=20,
        max_food_store=20,
    )

    state.apply(
        PlayerSaysMessage(
            ProtocolMessageType.PLAYER_SAYS,
            "PS\n5/0 MY NAME IS DOE",
            player_id=5,
            text="MY NAME IS DOE",
        )
    )

    observation = state.to_observation()
    assert observation.self.display_name == "EVE DOE"
    assert state.player_identities[5].display_name == "EVE DOE"
    assert observation.facts["player_names"] == {5: "EVE DOE"}

    chat_events = observation.facts["chat_events"]
    assert chat_events[-1]["speaker_name"] == "EVE DOE"
    assert chat_events[-1]["naming"]["display_name"] == "EVE DOE"
