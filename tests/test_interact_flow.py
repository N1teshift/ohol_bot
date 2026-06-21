from ohol_bot.action_pending import PendingAction
from ohol_bot.interact_flow import (
    approach_tile_orthogonal,
    can_interact_with_tile,
    decide_navigate_or_pickup,
)
from ohol_bot.model import ActionType, ObjectState, Observation, PlayerState, Tile


def _player(x: int, y: int, *, held_object_id: int | None = None) -> PlayerState:
    return PlayerState(
        player_id=5,
        tile=Tile(x, y),
        age=20.0,
        food_store=20,
        max_food_store=20,
        held_object_id=held_object_id,
        is_stationary=True,
    )


def _object(object_id: int, name: str, x: int, y: int) -> ObjectState:
    return ObjectState(object_id=object_id, name=name, tile=Tile(x, y))


def test_can_interact_with_tile_excludes_diagonal() -> None:
    assert can_interact_with_tile(Tile(0, 0), Tile(1, 0))
    assert not can_interact_with_tile(Tile(0, 0), Tile(1, 1))


def test_decide_navigate_or_pickup_moves_off_diagonal_before_pickup() -> None:
    stone = _object(33, "Stone", 8, 0)
    observation = Observation(
        tick=1,
        self=_player(7, 1),
        nearby_objects=(stone,),
    )
    pending = PendingAction()

    action, reason = decide_navigate_or_pickup(
        observation,
        stone,
        pending=pending,
        pickup_retry_reason=lambda *_args, **_kwargs: None,
        note_pickup_attempt=lambda *_args, **_kwargs: None,
        clear_pickup=lambda: None,
    )

    assert action.type is ActionType.MOVE_TO
    assert action.payload in ({"x": 8, "y": 1}, {"x": 7, "y": 0})
    assert reason == "move beside Stone"


def test_decide_navigate_or_pickup_picks_up_when_orthogonal() -> None:
    stone = _object(33, "Stone", 8, 0)
    observation = Observation(
        tick=1,
        self=_player(7, 0),
        nearby_objects=(stone,),
    )

    action, reason = decide_navigate_or_pickup(
        observation,
        stone,
        pending=PendingAction(),
        pickup_retry_reason=lambda *_args, **_kwargs: None,
        note_pickup_attempt=lambda *_args, **_kwargs: None,
        clear_pickup=lambda: None,
    )

    assert action.type is ActionType.PICK_UP
    assert action.payload == {"x": 8, "y": 0}
    assert reason == "pick up Stone"


def test_approach_tile_orthogonal_prefers_nearest_walkable() -> None:
    observation = Observation(
        tick=1,
        self=_player(5, 5),
        nearby_objects=(_object(32, "Big Hard Rock", 8, 0),),
    )

    approach = approach_tile_orthogonal(observation, Tile(8, 0))

    assert approach in (Tile(8, 1), Tile(7, 0))
