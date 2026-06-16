from ohol_bot.map_debug import MapRenderConfig, render_observation_map
from ohol_bot.model import ObjectState, Observation, PlayerState, Tile


def _player(player_id: int, x: int, y: int) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        tile=Tile(x, y),
        age=20.0,
        food_store=20,
        max_food_store=20,
    )


def test_render_observation_map_marks_core_tiles() -> None:
    observation = Observation(
        tick=1,
        self=_player(5, 0, 0),
        nearby_players=(_player(8, 2, 0),),
        nearby_objects=(
            ObjectState(63, "Maple Tree", Tile(1, 0)),
            ObjectState(31, "Berry", Tile(-1, 0), food_value=5),
        ),
        facts={
            "known_blocking_tiles": ((1, 0),),
            "avoid_targets": ((0, 1),),
            "follow_leader_tile": {"x": 2, "y": 0},
            "follow_target": {"x": 1, "y": 1},
            "last_move_path": ((0, -1),),
        },
    )

    rendered = render_observation_map(
        observation,
        config=MapRenderConfig(radius=2, max_object_labels=2),
    )

    assert "B" in rendered
    assert "L" in rendered
    assert "T" in rendered
    assert "#" in rendered
    assert "!" in rendered
    assert "!=danger" in rendered
    assert "*" in rendered
    assert "Berry" in rendered
