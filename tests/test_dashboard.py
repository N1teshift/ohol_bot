from ohol_bot.dashboard import explain_action, format_dashboard
from ohol_bot.model import Action, ActionType, Observation, ObjectState, PlayerState, Tile


def test_explain_hungry_explore_action() -> None:
    observation = Observation(
        tick=1,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18.0,
            food_store=3,
            max_food_store=15,
        ),
    )
    action = Action(ActionType.MOVE_TO, {"x": 1, "y": 0})

    reason = explain_action(observation, action)

    assert "hungry" in reason
    assert "(1, 0)" in reason


def test_format_dashboard_includes_hunger_and_food() -> None:
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient()
    client.self_player_id = 5
    observation = Observation(
        tick=3,
        self=PlayerState(
            player_id=5,
            tile=Tile(2, -1),
            age=20.0,
            food_store=17,
            max_food_store=20,
            yum_bonus=2,
            yum_multiplier=3,
            craving_food_id=100,
            craving_yum_bonus=4,
        ),
        nearby_objects=(
            ObjectState(object_id=100, name="wild berry", tile=Tile(3, -1), food_value=5),
        ),
        facts={"tracked_objects": 42, "world_state_ready": True},
    )

    frame = format_dashboard(
        client,
        observation,
        last_action=Action(ActionType.MOVE_TO, {"x": 3, "y": -1}),
        tick=2,
        mode="run-live",
    )

    assert "Stomach: 17/20" in frame.text
    assert "effective" not in frame.text
    assert "empty)" not in frame.text
    assert "Planner hungry: yes" in frame.text
    assert frame.text.index("Planner hungry") > frame.text.index("Planner\n")
    assert "Yum bonus: +2" in frame.text
    assert "Next Yum: object:100 +4" in frame.text
    assert "Age at last PU" not in frame.text
    assert "Craving:" not in frame.text
    assert "Nearest remembered food" not in frame.text
    assert "Tracked tiles: 42" in frame.text
    assert "planner tick 2" in frame.text
    assert "protocol msgs 3" in frame.text


def test_format_dashboard_shows_not_hungry_when_full() -> None:
    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient()
    observation = Observation(
        tick=1,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=20.0,
            food_store=20,
            max_food_store=20,
        ),
    )

    frame = format_dashboard(client, observation, tick=1)

    assert "Planner hungry: no" in frame.text
    assert "Holding:" in frame.text
    assert "Carried by:" in frame.text
    assert "Next Yum: none" in frame.text
