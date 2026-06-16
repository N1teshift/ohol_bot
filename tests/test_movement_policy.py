from ohol_bot.model import ActionType, ObjectState, Observation, PlayerState, Tile
from ohol_bot.movement_policy import FollowConfig, MovementFollowPolicy


def _player(
    player_id: int,
    x: int,
    y: int,
    *,
    held_object_id: int | None = None,
    held_object_name: str | None = None,
    held_pending: bool = False,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        tile=Tile(x, y),
        age=20.0,
        food_store=20,
        max_food_store=20,
        held_object_id=held_object_id,
        held_object_name=held_object_name,
        held_pending=held_pending,
        is_stationary=True,
    )


def _object(object_id: int, name: str, x: int, y: int) -> ObjectState:
    return ObjectState(object_id=object_id, name=name, tile=Tile(x, y))


def _chebyshev(a: Tile, b: Tile) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


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


def test_movement_policy_waits_when_same_tile_as_leader() -> None:
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
        nearby_players=(_player(8, 0, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["follow_reason"] == "close enough to leader"
    assert observation.facts["follow_target"] is None


def test_movement_policy_waits_when_adjacent_to_leader() -> None:
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
        nearby_players=(_player(8, 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["follow_reason"] == "close enough to leader"


def test_movement_policy_moves_to_adjacent_tile_when_leader_two_tiles_away() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 2, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert _chebyshev(Tile(action.payload["x"], action.payload["y"]), Tile(2, 0)) == 1


def test_movement_policy_treats_avoid_targets_as_soft_penalty() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 2, 0),),
        facts={
            "chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},),
            "avoid_targets": ((1, 0),),
            "blocked_tiles": (
                (1, -1),
                (1, 1),
                (2, -1),
                (2, 1),
                (3, -1),
                (3, 0),
                (3, 1),
            ),
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert Tile(action.payload["x"], action.payload["y"]) == Tile(1, 0)


def test_movement_policy_prefers_reachable_follow_candidate() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 2, 2),),
        facts={
            "chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},),
            "known_blocking_tiles": ((1, 0), (0, 1)),
        },
    )

    action = policy.decide(observation)
    target = Tile(action.payload["x"], action.payload["y"])

    assert action.type is ActionType.MOVE_TO
    assert target != Tile(1, 1)
    assert _chebyshev(target, Tile(2, 2)) == 1
    assert observation.facts["follow_candidate_tiles"][0]["reachable"] is True


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
        nearby_players=(_player(8, 8, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "follow"},)},
    )
    second_action = policy.decide(second)

    assert second_action.type is ActionType.MOVE_TO
    assert Tile(second_action.payload["x"], second_action.payload["y"]) == first_target


def test_movement_policy_enters_collect_from_chat_command() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(
            _object(100, "Round Stone", 5, 0),
            _object(101, "Sharp Stone", 3, 0),
        ),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "COLLECT sharp stone"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload == {"x": 3, "y": 0}
    assert policy.mode == "collect"
    assert policy.collect_requested_by == 8
    assert policy.collect_names == frozenset({"sharp stone"})
    assert observation.facts["movement_mode"] == "collect"
    assert observation.facts["collect_target_name"] == "Sharp Stone"
    assert observation.facts["collect_target"] == {"x": 3, "y": 0}


def test_movement_policy_collects_closest_matching_object() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(
            _object(101, "Sharp Stone", 5, 0),
            _object(102, "Sharp Stone", 2, 0),
            _object(103, "Round Stone", 1, 0),
        ),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload == {"x": 2, "y": 0}


def test_movement_policy_collect_picks_up_adjacent_item() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert action.payload == {"x": 1, "y": 0}
    assert policy.mode == "collect"
    assert observation.facts["collect_reason"] == "pick up Sharp Stone"


def test_movement_policy_collect_returns_idle_when_holding_item() -> None:
    policy = MovementFollowPolicy()
    first = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(first).type is ActionType.PICK_UP

    second = Observation(
        tick=2,
        self=_player(
            5,
            0,
            0,
            held_object_id=101,
            held_object_name="Sharp Stone",
        ),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    action = policy.decide(second)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert policy.collect_requested_by is None
    assert policy.collect_names == frozenset()
    assert second.facts["movement_mode"] == "idle"
    assert second.facts["collect_reason"] == "collect complete holding Sharp Stone"


def test_movement_policy_collect_waits_for_pending_pickup_confirmation() -> None:
    policy = MovementFollowPolicy()
    first = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(first).type is ActionType.PICK_UP

    pending = Observation(
        tick=2,
        self=_player(
            5,
            0,
            0,
            held_object_id=101,
            held_object_name="Sharp Stone",
            held_pending=True,
        ),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    action = policy.decide(pending)

    assert action.type is ActionType.WAIT
    assert policy.mode == "collect"
    assert pending.facts["movement_mode"] == "collect"
    assert pending.facts["collect_reason"] == "collect pickup pending"


def test_movement_policy_collect_throttles_pickup_retries() -> None:
    policy = MovementFollowPolicy(
        FollowConfig(
            collect_pickup_retry_cooldown_ticks=3,
        )
    )
    first = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(first).type is ActionType.PICK_UP

    retry_wait = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    wait_action = policy.decide(retry_wait)

    assert wait_action.type is ActionType.WAIT
    assert retry_wait.facts["collect_reason"] == "collect pickup retry wait 2"

    retry_ready = Observation(
        tick=4,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    retry_action = policy.decide(retry_ready)

    assert retry_action.type is ActionType.PICK_UP


def test_movement_policy_collect_keeps_retrying_pickup_until_holding_target() -> None:
    policy = MovementFollowPolicy(
        FollowConfig(
            collect_pickup_retry_cooldown_ticks=1,
        )
    )
    first = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(first).type is ActionType.PICK_UP

    second = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(second).type is ActionType.PICK_UP

    failed = Observation(
        tick=3,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    failed_action = policy.decide(failed)

    assert failed_action.type is ActionType.PICK_UP
    assert policy.mode == "collect"
    assert failed.facts["movement_mode"] == "collect"
    assert failed.facts["collect_reason"] == "pick up Sharp Stone"


def test_movement_policy_collect_drops_wrong_item_after_pickup_attempt() -> None:
    policy = MovementFollowPolicy()
    first = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(first).type is ActionType.PICK_UP

    wrong_item = Observation(
        tick=2,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    action = policy.decide(wrong_item)

    assert action.type is ActionType.DROP
    assert policy.mode == "collect"
    assert wrong_item.facts["collect_reason"] == "drop held Basket before collect"


def test_movement_policy_collect_drops_existing_held_item_first() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.DROP
    assert action.payload == {"x": 0, "y": 0}
    assert policy.mode == "collect"
    assert policy.collect_requested_by == 8
    assert observation.facts["collect_reason"] == "drop held Basket before collect"


def test_movement_policy_collect_drops_on_adjacent_empty_tile_when_current_occupied() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(
            _object(99, "Bowl", 0, 0),
            _object(101, "Sharp Stone", 2, 0),
        ),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.DROP
    assert action.payload == {"x": 0, "y": 1}
    assert observation.facts["collect_reason"] == "drop held Basket before collect"


def test_movement_policy_collect_waits_after_drop_before_pickup() -> None:
    policy = MovementFollowPolicy(
        FollowConfig(
            collect_drop_settle_ticks=3,
        )
    )
    held = Observation(
        tick=1,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(held).type is ActionType.DROP

    settling = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    wait_action = policy.decide(settling)

    assert wait_action.type is ActionType.WAIT
    assert settling.facts["collect_reason"] == "collect drop settle wait 2"

    ready = Observation(
        tick=4,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    collect_action = policy.decide(ready)

    assert collect_action.type is ActionType.PICK_UP
    assert collect_action.payload == {"x": 1, "y": 0}


def test_movement_policy_collect_keeps_retrying_drop_until_hands_free() -> None:
    policy = MovementFollowPolicy(
        FollowConfig(
            collect_drop_retry_cooldown_ticks=1,
        )
    )
    first = Observation(
        tick=1,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(first).type is ActionType.DROP

    second = Observation(
        tick=2,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    assert policy.decide(second).type is ActionType.DROP

    failed = Observation(
        tick=3,
        self=_player(
            5,
            0,
            0,
            held_object_id=200,
            held_object_name="Basket",
        ),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    failed_action = policy.decide(failed)

    assert failed_action.type is ActionType.DROP
    assert policy.mode == "collect"
    assert failed.facts["collect_reason"] == "drop held Basket before collect"


def test_movement_policy_idle_cancels_collect() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 0, 0),
            facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 0, 0),
        facts={
            "chat_events": (
                {"sequence": 1, "player_id": 8, "text": "collect sharp stone"},
                {"sequence": 2, "player_id": 8, "text": "idle"},
            )
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert policy.collect_requested_by is None
    assert observation.facts["collect_names"] == ()


def test_movement_policy_follow_overrides_collect() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 0, 0),
            facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 4, 0),),
        facts={
            "chat_events": (
                {"sequence": 1, "player_id": 8, "text": "collect sharp stone"},
                {"sequence": 2, "player_id": 8, "text": "follow"},
            )
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert policy.mode == "follow"
    assert policy.leader_id == 8
    assert policy.collect_requested_by is None
