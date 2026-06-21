from ohol_bot.model import ActionType, ObjectState, Observation, PlayerState, Tile
from ohol_bot.action_pending import PendingAction
from ohol_bot.movement_policy import (
    CampSlotProgress,
    CampStockState,
    FollowConfig,
    MovementFollowPolicy,
    StackCollectState,
)
from ohol_bot.tiles import chebyshev


def _player(
    player_id: int,
    x: int,
    y: int,
    *,
    age: float = 20.0,
    held_object_id: int | None = None,
    held_object_name: str | None = None,
    held_pending: bool = False,
    is_stationary: bool = True,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        tile=Tile(x, y),
        age=age,
        food_store=20,
        max_food_store=20,
        held_object_id=held_object_id,
        held_object_name=held_object_name,
        held_pending=held_pending,
        is_stationary=is_stationary,
    )


def _object(object_id: int, name: str, x: int, y: int) -> ObjectState:
    return ObjectState(object_id=object_id, name=name, tile=Tile(x, y))


def test_movement_policy_defaults_to_idle_wait() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(tick=1, self=_player(5, 0, 0))

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["movement_mode"] == "idle"


def test_movement_policy_replies_hello() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 6, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "hello"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.SAY
    assert action.payload["text"] == "HELLO"


def test_movement_policy_replies_with_short_greeting_when_young() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0, age=0.0),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "hi"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.SAY
    assert action.payload["text"] == "H"


def test_movement_policy_queues_hello_until_stationary() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0, is_stationary=False),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "hello"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy._pending_say == "HELLO"

    action = policy.decide(Observation(tick=2, self=_player(5, 0, 0, is_stationary=True)))

    assert action.type is ActionType.SAY
    assert action.payload["text"] == "HELLO"
    assert policy._pending_say is None


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
    assert chebyshev(Tile(action.payload["x"], action.payload["y"]), Tile(2, 0)) == 1


def test_movement_policy_treats_danger_tiles_as_soft_penalty() -> None:
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
    assert chebyshev(target, Tile(2, 2)) == 1
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
    assert action.payload == {"x": 2, "y": 0}
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
    assert action.payload == {"x": 1, "y": 0}


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


def test_movement_policy_collect_fast_retries_failed_pickup() -> None:
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

    retry = Observation(
        tick=2,
        self=_player(5, 0, 0),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect sharp stone"},)},
    )
    retry_action = policy.decide(retry)

    assert retry_action.type is ActionType.PICK_UP
    assert retry.facts["collect_reason"] == "pick up Sharp Stone"


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


def test_movement_policy_collect_waits_for_stationary_before_pickup() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "collect"
    policy.collect_names = frozenset({"sharp stone"})
    observation = Observation(
        tick=2,
        self=_player(5, 0, 0, is_stationary=False),
        nearby_objects=(_object(101, "Sharp Stone", 1, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["collect_reason"] == "wait stationary for pickup"
    assert policy._pickup_pending.tile is None


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


def test_movement_policy_enters_collect_stack_stone_from_chat_command() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 1, 0),
        nearby_players=(_player(8, 0, 0),),
        nearby_objects=(_object(33, "Stone", 2, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "COLLECT STACK STONE"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert policy.mode == "collect_stack"
    assert policy.collect_stack is not None
    assert policy.collect_stack.requested_by == 8
    assert policy.collect_stack.depot_origin == Tile(0, 0)
    assert policy.collect_stack.depot_tile == Tile(0, 1)
    assert observation.facts["movement_mode"] == "collect_stack"
    assert observation.facts["collect_stack"]["item_name"] == "Stone"
    assert observation.facts["collect_stack"]["depot_tile"] == {"x": 0, "y": 1}


def test_movement_policy_collect_stack_drops_first_stone_at_depot() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 1, 0),
            nearby_players=(_player(8, 0, 0),),
            nearby_objects=(_object(33, "Stone", 2, 0),),
            facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect stack stone"},)},
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 0, 1, held_object_id=33, held_object_name="Stone"),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect stack stone"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.DROP
    assert action.payload == {"x": 0, "y": 1}
    assert observation.facts["collect_reason"] == "start Stone stack 1/6"


def test_movement_policy_collect_stack_uses_stone_on_unknown_generated_depot() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(-9, 12),
        depot_tile=Tile(-9, 12),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, -9, 12, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(5404, "unknown:5404", -9, 12),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {
        "target_x": -9,
        "target_y": 12,
        "expect_empty_hands": True,
    }
    assert observation.facts["collect_reason"] == "add Stone to stack 1/6"


def test_movement_policy_collect_stack_uses_stone_on_existing_pile() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, 0, 1, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(661, "Stone Pile", 0, 1),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {
        "target_x": 0,
        "target_y": 1,
        "expect_empty_hands": True,
    }
    assert observation.facts["collect_reason"] == "add Stone to stack 1/6"


def test_movement_policy_collect_stack_counts_deposit_after_settle() -> None:
    policy = MovementFollowPolicy(FollowConfig(collect_stack_deposit_settle_ticks=3))
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        deposit_pending=PendingAction(tile=Tile(0, 1), sent_tick=2),
    )
    policy.mode = "collect_stack"
    settling = Observation(
        tick=3,
        self=_player(5, 0, 1),
        nearby_objects=(_object(661, "Stone Pile", 0, 1),),
    )

    wait_action = policy.decide(settling)

    assert wait_action.type is ActionType.WAIT
    assert policy.collect_stack is not None
    assert policy.collect_stack.deposited_count == 0
    assert settling.facts["collect_reason"] == "stack deposit settle wait 2"

    settled = Observation(
        tick=5,
        self=_player(5, 0, 1),
        nearby_objects=(_object(661, "Stone Pile", 0, 1),),
    )
    done_action = policy.decide(settled)

    assert done_action.type is ActionType.WAIT
    assert policy.collect_stack is not None
    assert policy.collect_stack.deposited_count == 1
    assert settled.facts["collect_reason"] == "stack waiting: no visible Stone"


def test_movement_policy_collect_stack_returns_to_depot_when_no_stones_visible() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
    )
    policy.mode = "collect_stack"
    observation = Observation(tick=2, self=_player(5, 4, 4))

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload == {"x": 0, "y": 1}
    assert observation.facts["collect_reason"] == "stack waiting: no visible Stone, return to depot"


def test_movement_policy_collect_stack_completes_at_six_deposits() -> None:
    policy = MovementFollowPolicy(FollowConfig(collect_stack_deposit_settle_ticks=1))
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        deposited_count=5,
        deposit_pending=PendingAction(tile=Tile(0, 1), sent_tick=1),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, 0, 1),
        nearby_objects=(_object(661, "Stone Pile", 0, 1),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert observation.facts["collect_reason"] == "stack complete 6/6 Stone"


def test_movement_policy_idle_cancels_collect_stack() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 1, 0),
            nearby_players=(_player(8, 0, 0),),
            facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "collect stack stone"},)},
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 1, 0),
        facts={
            "chat_events": (
                {"sequence": 1, "player_id": 8, "text": "collect stack stone"},
                {"sequence": 2, "player_id": 8, "text": "idle"},
            )
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert policy.collect_stack is None


def test_movement_policy_collect_stack_picks_from_nearby_stone_pile() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 0),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, 1, 0),
        nearby_objects=(_object(661, "Stone Pile", 2, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert action.payload == {"x": 2, "y": 0}
    assert observation.facts["collect_reason"] == "pick up Stone Pile for stack"


def test_movement_policy_collect_stack_ignores_depot_pile_uses_other_pile() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 0),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, 1, 0),
        nearby_objects=(
            _object(661, "Stone Pile", 0, 0),
            _object(662, "Stone Pile", 2, 0),
        ),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert action.payload == {"x": 2, "y": 0}


def test_movement_policy_collect_stack_waits_for_stationary_before_pile_pickup() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Stone",
        item_names=frozenset({"stone"}),
        pile_names=frozenset({"stone pile"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 0),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, 2, 0, is_stationary=False),
        nearby_objects=(_object(661, "Stone Pile", 2, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["collect_reason"] == "wait stationary for pickup"
    assert policy._pickup_pending.tile is None


def test_movement_policy_enters_collect_stack_limestone_from_chat_command() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 1, 0),
        nearby_players=(_player(8, 0, 0),),
        nearby_objects=(_object(674, "Limestone", 2, 0),),
        facts={
            "chat_events": (
                {"sequence": 1, "player_id": 8, "text": "collect stack limestone"},
            ),
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert policy.mode == "collect_stack"
    assert policy.collect_stack is not None
    assert policy.collect_stack.item_name == "Limestone"
    assert policy.collect_stack.item_names == frozenset({"limestone"})
    assert policy.collect_stack.pile_names == frozenset({"limestone pile"})


def test_movement_policy_collect_stack_limestone_uses_existing_pile() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Limestone",
        item_names=frozenset({"limestone"}),
        pile_names=frozenset({"limestone pile"}),
        loose_object_id=674,
        pile_object_id=2725,
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=2,
        self=_player(5, 0, 1, held_object_id=674, held_object_name="Limestone"),
        nearby_objects=(_object(2725, "Limestone Pile", 0, 1),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert observation.facts["collect_reason"] == "add Limestone to stack 1/6"


def test_parse_collect_stack_command_accepts_any_item_name() -> None:
    from ohol_bot.movement_chat import parse_collect_stack_command as _parse_collect_stack_command

    assert _parse_collect_stack_command("collect stack stone") == "stone"
    assert _parse_collect_stack_command("collect stack limestone") == "limestone"
    assert _parse_collect_stack_command("collect stack") is None
    assert _parse_collect_stack_command("collect stone") is None


def test_movement_policy_set_home_here_uses_speaker_tile_without_well() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 12, -3),),
        facts={
            "chat_events": (
                {
                    "sequence": 1,
                    "player_id": 8,
                    "text": "SET HOME HERE",
                    "speaker_tile": {"x": 12, "y": -3},
                },
            ),
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["set_home_tile"] == {"x": 12, "y": -3}
    assert observation.facts["set_home_radius"] == 12
    assert "no well/spring nearby" in observation.facts["follow_reason"]


def test_movement_policy_set_home_here_snaps_to_nearby_well() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 10, 0),),
        nearby_objects=(_object(662, "Shallow Well", 8, 0),),
        facts={
            "chat_events": (
                {
                    "sequence": 1,
                    "player_id": 8,
                    "text": "set home here",
                    "speaker_tile": {"x": 10, "y": 0},
                },
            ),
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert observation.facts["set_home_tile"] == {"x": 8, "y": 0}
    assert observation.facts["set_home_center_name"] == "shallow well"
    assert "shallow well" in observation.facts["follow_reason"]


def test_apply_policy_observation_effects_sets_world_home() -> None:
    from ohol_bot.protocol_client import OholProtocolClient
    from ohol_bot.runner import apply_policy_observation_effects

    client = OholProtocolClient()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        home=Tile(0, 0),
        facts={
            "set_home_tile": {"x": 8, "y": 0},
            "set_home_radius": 12,
            "set_home_center_name": "shallow well",
        },
    )

    apply_policy_observation_effects(client, observation)

    assert client.world_state.home_tile == Tile(8, 0)
    assert client.world_state.home_radius == 12
    assert client.world_state.home_center_name == "shallow well"
    assert observation.facts["home_tile"] == {"x": 8, "y": 0}
    assert observation.facts["home_radius"] == 12


def test_movement_policy_make_sharp_stone_from_chat() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "MAKE SHARP STONE"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "make_sharp_stone"
    assert policy.make_sharp_stone_requested_by == 8
    assert observation.facts["movement_mode"] == "make_sharp_stone"


def test_movement_policy_make_sharp_stone_picks_up_loose_stone() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_objects=(_object(33, "Stone", 1, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert action.payload == {"x": 1, "y": 0}
    assert observation.facts["collect_reason"] == "pick up Stone"


def test_movement_policy_make_sharp_stone_uses_rock_when_holding_stone() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    observation = Observation(
        tick=1,
        self=_player(5, 3, 0, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(32, "Big Hard Rock", 8, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload == {"x": 7, "y": 0}
    assert observation.facts["collect_reason"] == "move beside big hard rock"


def test_movement_policy_make_sharp_stone_picks_up_stone_from_diagonal() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    observation = Observation(
        tick=1,
        self=_player(5, 7, 1),
        nearby_objects=(_object(33, "Stone", 8, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload in ({"x": 8, "y": 1}, {"x": 7, "y": 0})
    assert observation.facts["collect_reason"] == "move beside Stone"


def test_movement_policy_knap_moves_off_diagonal_before_use() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    observation = Observation(
        tick=1,
        self=_player(5, 7, 1, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(32, "Big Hard Rock", 8, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.MOVE_TO
    assert action.payload in ({"x": 8, "y": 1}, {"x": 7, "y": 0})
    assert observation.facts["collect_reason"] == "move beside big hard rock"


def test_movement_policy_make_sharp_stone_knaps_when_adjacent_to_rock() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(32, "Big Hard Rock", 6, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {"target_x": 6, "target_y": 0}
    assert observation.facts["collect_reason"] == "knap stone on big hard rock"


def test_movement_policy_knap_waits_for_settle_before_retry() -> None:
    policy = MovementFollowPolicy(FollowConfig(knap_settle_ticks=4))
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    base = Observation(
        tick=1,
        self=_player(5, 5, 0, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(32, "Big Hard Rock", 6, 0),),
    )
    first = policy.decide(base)
    assert first.type is ActionType.USE

    wait_observation = Observation(
        tick=2,
        self=_player(5, 5, 0, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(_object(32, "Big Hard Rock", 6, 0),),
    )
    wait = policy.decide(wait_observation)
    assert wait.type is ActionType.WAIT
    assert "knap settle wait" in wait_observation.facts["collect_reason"]


def test_movement_policy_make_sharp_stone_completes_when_holding_result() -> None:
    policy = MovementFollowPolicy()
    policy.mode = "make_sharp_stone"
    policy.make_sharp_stone_requested_by = 8
    observation = Observation(
        tick=3,
        self=_player(5, 5, 1, held_object_id=34, held_object_name="Sharp Stone"),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert policy.make_sharp_stone_requested_by is None
    assert observation.facts["collect_reason"] == "make sharp stone complete"


def _camp_layout_facts(home_x: int = 0, home_y: int = 0) -> dict:
    from ohol_bot.camp_depot import build_camp_layout, camp_layout_to_facts

    return camp_layout_to_facts(build_camp_layout(Tile(home_x, home_y)))


def _camp_stack_catalog() -> tuple[dict, ...]:
    return (
        {
            "display_name": "Stone",
            "loose_names": ("stone",),
            "pile_names": ("stone pile",),
            "loose_object_id": 33,
            "pile_object_id": 661,
            "depot_target_ids": (),
            "source_target_ids": (),
            "query_aliases": ("stone", "stone pile"),
        },
        {
            "display_name": "Flint Chip",
            "loose_names": ("flint chip",),
            "pile_names": (),
            "loose_object_id": 135,
            "pile_object_id": None,
            "depot_target_ids": (),
            "source_target_ids": (),
            "query_aliases": ("flint", "flint chip", "flints"),
            "drop_only": True,
            "harvest": {
                "query": "flint",
                "display_name": "Flint Chip",
                "plant_object_ids": (133,),
                "plant_names": ("flint",),
                "dug_object_id": 150,
                "dug_names": ("flint chips",),
                "product_object_id": 135,
                "product_names": ("flint chip",),
                "tool_object_ids": (34,),
                "tool_names": ("sharp stone",),
                "query_aliases": ("flint", "flint chip", "flints"),
            },
        },
    )


def test_movement_policy_stock_camp_rejects_without_home() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 1, 0),),
        facts={"chat_events": ({"sequence": 1, "player_id": 8, "text": "stock camp"},)},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "idle"
    assert policy.camp_stock is None


def test_movement_policy_enters_stock_camp_from_chat_command() -> None:
    policy = MovementFollowPolicy()
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        home=Tile(0, 0),
        nearby_players=(_player(8, 1, 0),),
        facts={
            "chat_events": ({"sequence": 1, "player_id": 8, "text": "stock camp"},),
            "camp_layout": _camp_layout_facts(),
            "stack_collect_catalog": _camp_stack_catalog(),
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.WAIT
    assert policy.mode == "stock_camp"
    assert policy.camp_stock is not None
    assert len(policy.camp_stock.slots) == 8
    assert policy.camp_stock.slots[0].state.desired_count == 10
    assert policy.camp_stock.slots[0].state.depot_tile == Tile(-1, 9)
    assert observation.facts["movement_mode"] == "stock_camp"


def test_movement_policy_stock_camp_prioritizes_nearest_source() -> None:
    policy = MovementFollowPolicy()
    policy.decide(
        Observation(
            tick=1,
            self=_player(5, 0, 0),
            home=Tile(0, 0),
            nearby_players=(_player(8, 1, 0),),
            facts={
                "chat_events": ({"sequence": 1, "player_id": 8, "text": "stock camp"},),
                "camp_layout": _camp_layout_facts(),
                "stack_collect_catalog": _camp_stack_catalog(),
            },
        )
    )
    observation = Observation(
        tick=2,
        self=_player(5, 0, 0),
        home=Tile(0, 0),
        nearby_objects=(
            _object(33, "Stone", 5, 0),
            _object(135, "Flint Chip", 1, 0),
        ),
        facts={
            "chat_events": ({"sequence": 1, "player_id": 8, "text": "stock camp"},),
            "camp_layout": _camp_layout_facts(),
            "stack_collect_catalog": _camp_stack_catalog(),
        },
    )

    action = policy.decide(observation)

    assert action.type is ActionType.PICK_UP
    assert action.payload == {"x": 1, "y": 0}
    assert "camp slot 3" in observation.facts["collect_reason"]


def test_movement_policy_stock_camp_deposits_at_slot_tile() -> None:
    policy = MovementFollowPolicy()
    layout = _camp_layout_facts()
    policy.mode = "stock_camp"
    policy.stock_camp_requested_by = 8
    from ohol_bot.stack_collect import camp_stock_state_from_layout as _camp_stock_state_from_layout
    from ohol_bot.camp_depot import camp_layout_from_facts

    camp_layout = camp_layout_from_facts(layout)
    assert camp_layout is not None
    policy.camp_stock = _camp_stock_state_from_layout(
        Observation(
            tick=1,
            self=_player(5, -1, 9),
            facts={"stack_collect_catalog": _camp_stack_catalog()},
        ),
        camp_layout,
        requested_by=8,
    )
    observation = Observation(
        tick=2,
        self=_player(5, -1, 9, held_object_id=33, held_object_name="Stone"),
        facts={"stack_collect_catalog": _camp_stack_catalog()},
    )

    action = policy.decide(observation)

    assert action.type is ActionType.DROP
    assert action.payload == {"x": -1, "y": 9}
    assert "camp slot 1" in observation.facts["collect_reason"]


def _harvest_catalog() -> tuple[dict, ...]:
    return (
        {
            "query": "burdock",
            "display_name": "Burdock Root",
            "plant_object_ids": (804,),
            "plant_names": ("burdock",),
            "dug_object_id": 806,
            "dug_names": ("dug burdock",),
            "product_object_id": 807,
            "product_names": ("burdock root",),
            "tool_object_ids": (34, 722),
            "tool_names": ("sharp stone", "@ shallow digger"),
            "query_aliases": ("burdock", "burdock root"),
        },
        {
            "query": "wild carrot",
            "display_name": "Wild Carrot",
            "plant_object_ids": (404,),
            "plant_names": ("wild carrot",),
            "dug_object_id": 39,
            "dug_names": ("dug wild carrot",),
            "product_object_id": 40,
            "product_names": ("wild carrot",),
            "tool_object_ids": (34, 722),
            "tool_names": ("sharp stone", "@ shallow digger"),
            "query_aliases": ("wild carrot",),
        },
    )


def test_movement_policy_harvest_digs_burdock_with_sharp_stone() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Burdock Root",
        item_names=frozenset({"burdock root", "burdock"}),
        pile_names=frozenset({"pile of burdock roots"}),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=807,
        harvest_rule=_harvest_catalog()[0],
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0, held_object_id=34, held_object_name="Sharp Stone"),
        nearby_objects=(_object(804, "Burdock", 6, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {"target_x": 6, "target_y": 0}


def test_movement_policy_harvest_uses_sharp_stone_on_adjacent_burdock() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Burdock Root",
        item_names=frozenset({"burdock root", "burdock"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=807,
        harvest_rule=_harvest_catalog()[0],
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0, held_object_id=34, held_object_name="Sharp Stone"),
        nearby_objects=(_object(804, "Burdock", 6, 0),),
    )
    policy._harvest_work_tile = Tile(6, 0)

    action = policy.decide(
        Observation(
            tick=2,
            self=_player(5, 5, 0, held_object_id=34, held_object_name="Sharp Stone"),
            nearby_objects=(_object(804, "Burdock", 6, 0),),
        )
    )

    assert action.type is ActionType.USE
    assert action.payload == {"target_x": 6, "target_y": 0}


def test_movement_policy_harvest_drops_tool_before_gathering_dug_plant() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Burdock Root",
        item_names=frozenset({"burdock root"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=807,
        harvest_rule=_harvest_catalog()[0],
    )
    policy.mode = "collect_stack"
    policy._harvest_work_tile = Tile(6, 0)
    observation = Observation(
        tick=3,
        self=_player(5, 6, 0, held_object_id=34, held_object_name="Sharp Stone"),
        nearby_objects=(_object(806, "Dug Burdock", 6, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.DROP


def test_movement_policy_harvest_gathers_product_from_dug_tile() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Burdock Root",
        item_names=frozenset({"burdock root"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=807,
        harvest_rule=_harvest_catalog()[0],
    )
    policy.mode = "collect_stack"
    policy._harvest_work_tile = Tile(6, 0)
    observation = Observation(
        tick=4,
        self=_player(5, 5, 0),
        nearby_objects=(_object(806, "Dug Burdock", 6, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {"target_x": 6, "target_y": 0}


def test_movement_policy_harvest_knaps_round_stone_when_needed() -> None:
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Wild Carrot",
        item_names=frozenset({"wild carrot"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=40,
        harvest_rule=_harvest_catalog()[1],
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=1,
        self=_player(5, 6, 0, held_object_id=33, held_object_name="Stone"),
        nearby_objects=(
            _object(404, "Wild Carrot", 8, 0),
            _object(32, "Big Hard Rock", 7, 0),
        ),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {"target_x": 7, "target_y": 0}


def test_nearest_harvest_plant_ignores_loose_wild_carrot_product() -> None:
    from ohol_bot.stack_collect import _nearest_harvest_plant

    rule = _harvest_catalog()[1]
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0),
        nearby_objects=(_object(40, "Wild Carrot", 0, 1),),
    )

    assert _nearest_harvest_plant(observation, rule, Tile(0, 1)) is None


def test_nearest_stack_source_matches_harvest_product_by_id_only() -> None:
    from ohol_bot.stack_collect import nearest_stack_source as _nearest_stack_source

    state = StackCollectState(
        requested_by=8,
        item_name="Wild Carrot",
        item_names=frozenset({"wild carrot"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=40,
        harvest_rule=_harvest_catalog()[1],
    )
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0),
        nearby_objects=(
            _object(40, "Wild Carrot", 6, 0),
            _object(404, "Wild Carrot", 8, 0),
        ),
    )

    selected = _nearest_stack_source(observation, state)

    assert selected is not None
    assert selected.object_id == 40


def test_stock_camp_does_not_use_sharp_stone_on_depot_carrot() -> None:
    policy = MovementFollowPolicy()
    slot_state = StackCollectState(
        requested_by=8,
        item_name="Wild Carrot",
        item_names=frozenset({"wild carrot"}),
        pile_names=frozenset(),
        depot_origin=None,
        depot_tile=Tile(0, 1),
        loose_object_id=40,
        desired_count=6,
        harvest_rule=_harvest_catalog()[1],
    )
    policy.mode = "stock_camp"
    policy.camp_stock = CampStockState(
        requested_by=8,
        slots=(CampSlotProgress(slot_id=1, state=slot_state),),
    )
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0),
        nearby_objects=(
            _object(40, "Wild Carrot", 0, 1),
            _object(34, "Sharp Stone", 5, 6),
        ),
    )

    action = policy.decide(observation)

    if action.type is ActionType.USE:
        assert action.payload != {"target_x": 0, "target_y": 1}


def test_should_prefer_nearby_loose_carrot_over_dug_plant() -> None:
    from ohol_bot.stack_collect import _should_prefer_loose_over_harvest

    rule = _harvest_catalog()[1]
    state = StackCollectState(
        requested_by=8,
        item_name="Wild Carrot",
        item_names=frozenset({"wild carrot"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=40,
        harvest_rule=rule,
    )
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0),
        nearby_objects=(
            _object(40, "Wild Carrot", 6, 0),
            _object(39, "Dug Wild Carrot", 12, 0),
        ),
    )

    assert _should_prefer_loose_over_harvest(observation, state) is True


def test_movement_policy_harvest_knaps_flint_outcrop_with_sharp_stone() -> None:
    flint_rule = _camp_stack_catalog()[1]["harvest"]
    policy = MovementFollowPolicy()
    policy.collect_stack = StackCollectState(
        requested_by=8,
        item_name="Flint Chip",
        item_names=frozenset({"flint chip"}),
        pile_names=frozenset(),
        depot_origin=Tile(0, 0),
        depot_tile=Tile(0, 1),
        loose_object_id=135,
        drop_only=True,
        harvest_rule=flint_rule,
    )
    policy.mode = "collect_stack"
    observation = Observation(
        tick=1,
        self=_player(5, 5, 0, held_object_id=34, held_object_name="Sharp Stone"),
        nearby_objects=(_object(133, "Flint", 6, 0),),
    )

    action = policy.decide(observation)

    assert action.type is ActionType.USE
    assert action.payload == {"target_x": 6, "target_y": 0}


def test_stock_camp_drops_surplus_carrot_without_repick_loop() -> None:
    policy = MovementFollowPolicy()
    slot_state = StackCollectState(
        requested_by=8,
        item_name="Wild Carrot",
        item_names=frozenset({"wild carrot"}),
        pile_names=frozenset(),
        depot_origin=None,
        depot_tile=Tile(0, 1),
        loose_object_id=40,
        desired_count=6,
        deposited_count=6,
        harvest_rule=_harvest_catalog()[1],
    )
    policy.mode = "stock_camp"
    policy.camp_stock = CampStockState(
        requested_by=8,
        slots=(CampSlotProgress(slot_id=5, state=slot_state),),
    )
    holding = Observation(
        tick=1,
        self=_player(5, 5, 0, held_object_id=40, held_object_name="Wild Carrot"),
        nearby_objects=(_object(40, "Wild Carrot", 6, 0),),
    )

    drop_action = policy.decide(holding)

    assert drop_action.type is ActionType.DROP
    assert "surplus" in holding.facts["collect_reason"]

    after_drop = Observation(
        tick=2,
        self=_player(5, 5, 0),
        nearby_objects=(_object(40, "Wild Carrot", 6, 0),),
    )
    wait_action = policy.decide(after_drop)

    assert wait_action.type is ActionType.WAIT
    assert after_drop.facts["collect_reason"] == "stock camp complete"
    assert policy.mode == "idle"

