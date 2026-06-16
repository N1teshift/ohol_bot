from pathlib import Path

from ohol_bot.game_data import load_game_data, parse_object_file, parse_transition_file


def test_parse_object_file(tmp_path: Path) -> None:
    object_file = tmp_path / "10.txt"
    object_file.write_text(
        "\n".join(
            [
                "id=10",
                "Test Berry",
                "blocksWalking=0,leftBlockingRadius=0,rightBlockingRadius=0",
                "foodValue=5",
                "numUses=2,1.000000",
            ]
        ),
        encoding="utf-8",
    )

    obj = parse_object_file(object_file)

    assert obj.object_id == 10
    assert obj.name == "Test Berry"
    assert obj.food_value == 5
    assert obj.num_uses == 2
    assert obj.blocks_walking is False
    assert obj.left_blocking_radius == 0
    assert obj.right_blocking_radius == 0


def test_parse_object_blocking_radii(tmp_path: Path) -> None:
    object_file = tmp_path / "11.txt"
    object_file.write_text(
        "\n".join(
            [
                "id=11",
                "Test Tree",
                "blocksWalking=1,leftBlockingRadius=2,rightBlockingRadius=1",
            ]
        ),
        encoding="utf-8",
    )

    obj = parse_object_file(object_file)

    assert obj.blocks_walking is True
    assert obj.left_blocking_radius == 2
    assert obj.right_blocking_radius == 1


def test_parse_transition_file(tmp_path: Path) -> None:
    transition_file = tmp_path / "1_2_LT.txt"
    transition_file.write_text("3 4 0 0.000000 0.000000 0 0 0 1 0 0\n", encoding="utf-8")

    transition = parse_transition_file(transition_file)

    assert transition is not None
    assert transition.actor_id == 1
    assert transition.target_id == 2
    assert transition.new_actor_id == 3
    assert transition.new_target_id == 4


def test_load_game_data_can_skip_transitions(tmp_path: Path) -> None:
    objects_path = tmp_path / "objects"
    transitions_path = tmp_path / "transitions"
    objects_path.mkdir()
    transitions_path.mkdir()
    (objects_path / "10.txt").write_text("id=10\nTest Berry\n", encoding="utf-8")
    (transitions_path / "1_2_LT.txt").write_text(
        "3 4 0 0.000000 0.000000 0 0 0 1 0 0\n",
        encoding="utf-8",
    )

    full = load_game_data(tmp_path)
    skipped = load_game_data(tmp_path, include_transitions=False)

    assert len(full.transitions) == 1
    assert skipped.transitions == ()
    assert skipped.objects[10].name == "Test Berry"


def test_build_stack_collect_catalog_from_runtime_objects() -> None:
    from ohol_bot.game_data import build_stack_collect_catalog, load_game_data

    root = Path(".ohol_runtime/server")
    if not (root / "objects").exists():
        return

    game_data = load_game_data(root)
    catalog = build_stack_collect_catalog(game_data)
    by_loose_id = {
        rule["loose_object_id"]: rule for rule in catalog if rule.get("loose_object_id")
    }

    assert 33 in by_loose_id
    assert by_loose_id[33]["display_name"] == "Stone"
    assert 674 in by_loose_id
    assert by_loose_id[674]["display_name"] == "Limestone"
