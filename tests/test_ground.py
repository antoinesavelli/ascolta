"""Test 1: the grounding check finds real quotes and visibly flags everything else."""

from __future__ import annotations

from conftest import segment

from ascolta.ground import check

SEGMENTS = [
    segment(10, "So anyway, I will call the bank on Monday morning and ask about the loan."),
    segment(15, "Then we can talk about the house, maybe"),
    segment(19, "next week when you are back."),
    segment(
        40,
        "Je vais appeler la banque lundi matin.",
        en="I am going to call the bank on Monday morning.",
        lang="fr",
    ),
    segment(60, "The heating is broken again and nobody has fixed it.", flags=["mixed"]),
]


def label(quote: str, ts: str) -> str:
    return check({"quote": quote, "ts": ts}, SEGMENTS, duration=120)


def test_exact_quote_inside_a_long_segment_is_found() -> None:
    assert label("I will call the bank on Monday morning", "00:10") == "quote found"


def test_quote_spanning_two_segments_is_found() -> None:
    assert label("talk about the house maybe next week", "00:16") == "quote found"


def test_paraphrase_is_not_found() -> None:
    assert label("He promised to phone his bank early next week", "00:10") == "⚠ quote not found"


def test_right_quote_at_the_wrong_time_is_not_found() -> None:
    assert label("I will call the bank on Monday morning", "01:50") == "⚠ quote not found"


def test_uncited_item_is_flagged() -> None:
    assert check({"text": "A claim", "quote": "", "ts": ""}, SEGMENTS, duration=120) == "⚠ uncited"


def test_short_quote_is_flagged() -> None:
    assert label("call the bank", "00:10") == "⚠ quote too short"


def test_match_only_in_the_english_line_is_labelled_as_translation() -> None:
    assert label("going to call the bank on Monday morning", "00:40") == "found in translation"


def test_bad_timestamps_are_flagged() -> None:
    assert label("I will call the bank on Monday morning", "202:00") == "⚠ bad timestamp"
    assert label("I will call the bank on Monday morning", "00:75") == "⚠ bad timestamp"


def test_quote_on_a_flagged_segment_carries_the_flag() -> None:
    assert label("the heating is broken again and nobody", "01:00") == "quote found ⚠ mixed"
