from ohol_bot.model import ActionType, Observation, PlayerState, Tile
from ohol_bot.movement_policy import FollowConfig, MovementFollowPolicy


def _player(player_id: int, x: int, y: int) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        tile=Tile(x, y),
        age=20.0,
        food_store=20,
        max_food_store=20,
        is_stationary=True,
    )


def test_movement_policy_defaults_to_idle_wait() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(tick=1, self=_player(5, 0, 0))

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["movement_mode"] == "idle"


def test_movement_policy_enters_follow_from_chat_command() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 6, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert policy.mode == "follow"
    assert policy.leader_id == 8
    assert observation.facts["follow_leader_id"] == 8
    assert observation.facts["follow_target"] is not None


def test_movement_policy_waits_inside_follow_distance_band() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 0, 0),
            nearby_players=(_player(8, 6, 0),),
            facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 2, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["follow_reason"] == "inside follow distance band"


def test_movement_policy_stop_follow_returns_to_idle() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 0, 0),
            nearby_players=(_player(8, 6, 0),),
            facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 6, 0),),
        facts={
            "chat_events": (
                {"sequence": 1, "player_id": 8, "text": "follow"},
                {"sequence": 2, "player_id": 8, "text": "stop follow"},
            )
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert policy.leader_id is None


def test_movement_policy_reuses_recent_follow_target() -> None:
    policy = MovementFollowPolicy(FollowConfig(retarget_cooldown_ticks=10))
    first = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 8, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )
    first_action = policy.decide(first)
    first_target = Tile(first_action.payload["x"], first_action.payload["y"])

    second = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 8, 1),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )
    second_action = policy.decide(second)

    assert second_action.type is ActionType.MOVE_TO
    assert Tile(second_action.payload["x"], second_action.payload["y"]) == first_target
