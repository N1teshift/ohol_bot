from ohol_bot.client import MockBotClient
from ohol_bot.model import ActionType, ObjectState, Observation, PlayerState, Tile
from ohol_bot.planner import SurvivalPlanner
from ohol_bot.runner import run_episode


def test_survival_planner_moves_to_food_when_hungry() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=3,
            max_food_store=10,
        ),
        nearby_objects=(
            ObjectState(
                object_id=100,
                name="wild berry",
                tile=Tile(2, 0),
                food_value=5,
            ),
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.survived is True
    assert result.actions[0].type is ActionType.MOVE_TO
    assert result.actions[0].payload == {"x": 2, "y": 0}


def test_survival_planner_eats_held_food_when_hungry() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=3,
            max_food_store=10,
            held_object_id=100,
            held_food_value=5,
            held_object_name="wild berry",
            is_stationary=True,
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.USE_SELF


def test_survival_planner_waits_to_eat_when_too_young() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=0.0,
            food_store=4,
            max_food_store=20,
            held_object_id=31,
            held_food_value=3,
            held_object_name="Gooseberry",
            is_stationary=True,
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.WAIT


def test_survival_planner_waits_to_eat_while_moving() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=4,
            max_food_store=20,
            held_object_id=31,
            held_food_value=3,
            held_object_name="Gooseberry",
            is_stationary=False,
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.WAIT


def test_survival_planner_waits_while_moving_to_food() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(7, 0),
            age=18,
            food_store=14,
            max_food_store=20,
            is_stationary=False,
        ),
        nearby_objects=(
            ObjectState(
                object_id=31,
                name="Gooseberry",
                tile=Tile(11, 0),
                food_value=3,
            ),
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.WAIT


def test_survival_planner_waits_when_being_carried() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=0.5,
            food_store=1,
            max_food_store=10,
            held_by_player_id=42,
        ),
        nearby_objects=(
            ObjectState(
                object_id=100,
                name="wild berry",
                tile=Tile(0, 0),
                food_value=5,
            ),
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.WAIT


def test_survival_planner_waits_when_stomach_is_full() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=10,
            max_food_store=10,
        ),
        nearby_objects=(
            ObjectState(
                object_id=100,
                name="wild berry",
                tile=Tile(0, 0),
                food_value=5,
            ),
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.WAIT


def test_survival_planner_seeks_food_with_one_pip_missing() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=9,
            max_food_store=10,
        ),
        nearby_objects=(
            ObjectState(
                object_id=100,
                name="wild berry",
                tile=Tile(1, 0),
                food_value=5,
            ),
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.PICK_UP
    assert result.actions[0].payload == {"x": 1, "y": 0}


def test_survival_planner_eats_when_server_reports_held_yum_only() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=9,
            max_food_store=10,
            held_yum=True,
            is_stationary=True,
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.USE_SELF


def test_survival_planner_picks_up_adjacent_food_even_when_avoided() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(2, 25),
            age=18,
            food_store=3,
            max_food_store=10,
            is_stationary=True,
        ),
        nearby_objects=(
            ObjectState(
                object_id=31,
                name="Gooseberry",
                tile=Tile(2, 24),
                food_value=3,
            ),
        ),
        home=Tile(0, 0),
        facts={"avoid_targets": ((2, 24),)},
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.PICK_UP
    assert result.actions[0].payload == {"x": 2, "y": 24}


def test_survival_planner_drops_non_food_before_forage() -> None:
    observation = Observation(
        tick=0,
        self=PlayerState(
            player_id=1,
            tile=Tile(0, 0),
            age=18,
            food_store=3,
            max_food_store=10,
            held_object_id=999,
            is_stationary=True,
        ),
        nearby_objects=(
            ObjectState(
                object_id=31,
                name="Gooseberry",
                tile=Tile(1, 0),
                food_value=3,
            ),
        ),
        home=Tile(0, 0),
    )
    client = MockBotClient([observation])

    result = run_episode(client, SurvivalPlanner(), max_ticks=1)

    assert result.actions[0].type is ActionType.DROP
