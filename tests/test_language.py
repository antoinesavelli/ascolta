"""Test 5: language choice per chunk, the function-word relabel, and translation of a relabelled segment."""

from __future__ import annotations

import shutil

import pytest
from conftest import cli, clip, fake_call, load, segment

from ascolta.translate import relabel


def test_french_text_labelled_english_is_relabelled() -> None:
    assert relabel("je pense que c'est une bonne idée pour demain matin") == "fr"


def test_spanish_text_labelled_english_is_relabelled() -> None:
    assert relabel("pero yo creo que eso está muy bien para el viernes") == "es"


def test_english_stays_english() -> None:
    assert relabel("I will call the bank on Monday and let me know if a letter comes") is None
    assert relabel("Le Mans is a city; we drove there on a Tuesday") is None


@pytest.mark.gpu
def test_english_then_german_flags_the_other_language(data) -> None:
    from ascolta.calls import new_call

    call = new_call("tester")
    shutil.copy(clip("multilingual.mp3"), call / "audio.mp3")
    result = cli("stage", "transcribe", str(call))
    assert result.returncode == 0, result.stderr
    segments = load(call / "segments.json")["segments"]
    assert segments[0]["lang"] == "en" and "other language" not in segments[0]["flags"]
    assert any("other language" in s["flags"] for s in segments), "German was not flagged"


@pytest.mark.ollama
def test_relabelled_french_segment_is_translated(data) -> None:
    from ascolta.calls import write_json

    call = fake_call(data, [])
    french = segment(5, "Je vais appeler la banque lundi pour le prêt de la maison.")
    write_json(call / "segments.json", {"duration_s": 20, "segments": [french]})
    result = cli("stage", "translate", str(call))
    assert result.returncode == 0, result.stderr
    out = load(call / "transcript.json")["segments"][0]
    assert out["lang"] == "fr" and "language relabelled" in out["flags"]
    assert out["en"] and "bank" in out["en"].casefold()
