import math

from ohol_bot.speech import fit_say_from_candidates, fit_say_text, say_limit_for_age

def test_say_limit_matches_ohol_curve() -> None:
    assert say_limit_for_age(0.0) == 1
    assert say_limit_for_age(1.0) == 2
    assert say_limit_for_age(7.9) == 8
    assert say_limit_for_age(8.0) == 9
    assert say_limit_for_age(16.0) == 66
    assert say_limit_for_age(18.0) == 67


def test_fit_say_text_uppercases_and_rejects_too_long() -> None:
    assert fit_say_text("hi", age=1.0) == "HI"
    assert fit_say_text("hi", age=0.5) is None
    assert fit_say_text("hello", age=3.0) is None


def test_fit_say_from_candidates_prefers_longest_that_fits() -> None:
    assert fit_say_from_candidates(("HELLO", "HI", "H"), age=20.0) == "HELLO"
    assert fit_say_from_candidates(("HELLO", "HI", "H"), age=1.0) == "HI"
    assert fit_say_from_candidates(("HELLO", "HI", "H"), age=0.0) == "H"
    assert fit_say_from_candidates(("HELLO",), age=0.0) is None
