from ohol_bot.runner import _mode_label, _parse_control_mode_switch


def test_parse_control_mode_switch() -> None:
    assert _parse_control_mode_switch("manual") == "manual"
    assert _parse_control_mode_switch("AUTO") == "auto"
    assert _parse_control_mode_switch(" move 5 north ") is None


def test_mode_label_reflects_control_mode() -> None:
    assert _mode_label("play", "auto", None) == "play [auto]"
    assert _mode_label("play", "manual", None) == "play [manual]"
