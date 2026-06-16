from ohol_bot.dashboard import DashboardRateTracker, explain_action, format_dashboard
from ohol_bot.model import Action, ActionType, Observation, ObjectState, PlayerState, Tile


def test_explain_move_action_uses_follow_reason() -> None:
    observation = Observation(
        tick=1,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18.0,
            food_store=3,
            max_food_store=15,
        ),
        facts={"follow_reason": "move adjacent to leader"},
    )
    action = Action(ActionType.MOVE_TO, {"x": 1, "y": 0})

    reason = explain_action(observation, action)

    assert "move adjacent to leader" in reason
    assert "(1, 0)" in reason


def test_format_dashboard_includes_movement_follow_telemetry() -> None:
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
        nearby_players=(
            PlayerState(
                player_id=8,
                tile=Tile(4, -1),
                age=20.0,
                food_store=20,
                max_food_store=20,
            ),
        ),
        nearby_objects=(
            ObjectState(object_id=100, name="wild berry", tile=Tile(3, -1), food_value=5),
        ),
        facts={
            "tracked_objects": 42,
            "world_state_ready": True,
            "movement_mode": "follow",
            "follow_leader_id": 8,
            "follow_leader_tile": {"x": 4, "y": -1},
            "follow_leader_distance": 2,
            "follow_target": {"x": 3, "y": -1},
            "follow_reason": "move adjacent to leader",
            "chat_events": (
                {"sequence": 1, "player_id": 8, "text": "FOLLOW"},
            ),
        },
    )

    frame = format_dashboard(
        client,
        observation,
        last_action=Action(ActionType.MOVE_TO, {"x": 3, "y": -1}),
        tick=2,
        mode="run-live",
    )

    assert "Actions" in frame.text
    assert "Goal: follow target (3, -1), leader 8 at (4, -1), dist=2" in frame.text
    assert "Last chat: player 8: FOLLOW" in frame.text
    assert "Status:" in frame.text
    assert "Action blocked by: nothing" in frame.text
    assert "player 8" in frame.text
    assert "Other players nearby" not in frame.text
    assert "effective" not in frame.text
    assert "empty)" not in frame.text
    assert "Planner hungry" not in frame.text
    assert "Yum bonus" not in frame.text
    assert "Next Yum" not in frame.text
    assert "Age at last PU" not in frame.text
    assert "Craving:" not in frame.text
    assert "Nearest remembered food" not in frame.text
    assert "Tracked tiles: 42" in frame.text
    assert "planner tick 2" in frame.text
    assert "world tick 3" in frame.text
    assert "KA pings 0" in frame.text
    assert "Actions sent: 0" in frame.text
    assert "Connection" not in frame.text


def test_format_dashboard_shows_idle_movement_mode() -> None:
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

    assert "Goal: none" in frame.text
    assert "Can move/self-act:" in frame.text
    assert "Stationary:" in frame.text
    assert "Holding:" in frame.text
    assert "Carried by:" in frame.text
    assert "Next Yum" not in frame.text


def test_format_dashboard_includes_collect_goal() -> None:
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
        ),
        facts={
            "movement_mode": "collect",
            "collect_names": ("stone",),
            "collect_target_name": "Stone",
            "collect_target": {"x": 4, "y": 28},
            "collect_reason": "move to Stone",
        },
    )

    frame = format_dashboard(
        client,
        observation,
        last_action=Action(ActionType.MOVE_TO, {"x": 4, "y": 28}),
        tick=2,
        mode="run-live",
    )

    assert "Goal: trying to collect Stone at (4, 28)" in frame.text
    assert "Status: moving to (4, 28) (move to Stone)" in frame.text


def test_format_dashboard_includes_collect_stack_progress() -> None:
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
        ),
        facts={
            "movement_mode": "collect_stack",
            "collect_reason": "add Stone to stack 3/6",
            "collect_stack": {
                "item_name": "Stone",
                "deposited_count": 2,
                "desired_count": 6,
                "depot_tile": {"x": 4, "y": 28},
            },
        },
    )

    frame = format_dashboard(
        client,
        observation,
        last_action=Action(
            ActionType.USE,
            {"target_x": 4, "target_y": 28, "expect_empty_hands": True},
        ),
        tick=2,
        mode="run-live",
    )

    assert "Goal: collect stack Stone at (4, 28) (2/6)" in frame.text
    assert "Status: using tile (4, 28) (add Stone to stack 3/6)" in frame.text


def test_dashboard_rate_tracker_extrapolates_to_five_second_window() -> None:
    tracker = DashboardRateTracker()

    rates = tracker.update(
        planner_tick=0,
        world_tick=0,
        server_frames=0,
        ka_pings=0,
        now=0.0,
    )
    assert rates["planner"] == 0.0

    rates = tracker.update(
        planner_tick=5,
        world_tick=5,
        server_frames=5,
        ka_pings=1,
        now=2.5,
    )

    assert rates["planner"] == 10.0
    assert rates["world"] == 10.0
    assert rates["server_frames"] == 10.0
    assert rates["ka"] == 2.0


def test_format_dashboard_shows_per_five_second_rates() -> None:
    from unittest.mock import patch

    from ohol_bot.protocol_client import OholProtocolClient

    client = OholProtocolClient()
    client.frame_paced = True
    client.server_frames = 10
    client._sent_keep_alives = 2
    observation = Observation(
        tick=10,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=20.0,
            food_store=20,
            max_food_store=20,
        ),
    )
    tracker = DashboardRateTracker()
    tracker.update(
        planner_tick=0,
        world_tick=0,
        server_frames=0,
        ka_pings=0,
        now=0.0,
    )
    client.dashboard_rate_tracker = tracker

    with patch("ohol_bot.dashboard.time.monotonic", return_value=2.5):
        frame = format_dashboard(client, observation, tick=5, mode="run-live")

    assert "planner tick 5 (+10/5s)" in frame.text
    assert "world tick 10 (+20/5s)" in frame.text
    assert "server frames 10 (+20/5s)" in frame.text
    assert "KA pings 2 (+4/5s)" in frame.text
