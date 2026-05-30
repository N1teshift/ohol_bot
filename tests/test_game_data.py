from pathlib import Path

from ohol_bot.game_data import parse_object_file, parse_transition_file


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


def test_parse_transition_file(tmp_path: Path) -> None:
    transition_file = tmp_path / "1_2_LT.txt"
    transition_file.write_text("3 4 0 0.000000 0.000000 0 0 0 1 0 0\n", encoding="utf-8")

    transition = parse_transition_file(transition_file)

    assert transition is not None
    assert transition.actor_id == 1
    assert transition.target_id == 2
    assert transition.new_actor_id == 3
    assert transition.new_target_id == 4
