"""Test 8: failures are marked ⚠, and neither logs nor run.json carry transcript text, even on a crash.

The Ollama client is replaced here: it is the external dependency, not the unit under test.
"""

from __future__ import annotations

import pytest
from conftest import cli as run_cli
from conftest import fake_call, load, segment

from ascolta import calls, cli, ollama

SECRET = "Le code du portail est quatre deux sept"


def test_bad_timestamp_is_marked_and_the_rest_stands(data) -> None:
    call = fake_call(
        data, [segment(5, "I will call the bank on Monday morning, I promise.")], duration=30
    )
    calls.write_json(
        call / "summary.json",
        {
            "summary": [],
            "action_items": [
                {
                    "owner": "remote",
                    "text": "Call the bank",
                    "ts": "202:00",
                    "quote": "I will call the bank on Monday",
                },
                {
                    "owner": "remote",
                    "text": "Call the bank",
                    "ts": "00:05",
                    "quote": "I will call the bank on Monday",
                },
            ],
        },
    )
    result = run_cli("stage", "ground", str(call))
    assert result.returncode == 0, result.stderr
    report = (call / "summary.md").read_text()
    assert "⚠ bad timestamp" in report and "— quote found" in report
    assert "bank" not in (result.stdout + result.stderr)


@pytest.fixture
def french_call(data, monkeypatch):
    call = fake_call(data, [])
    calls.write_json(
        call / "segments.json", {"duration_s": 9, "segments": [segment(1, SECRET, lang="fr")]}
    )
    monkeypatch.setattr(calls, "wait_for_vram", lambda stage, label: None)
    monkeypatch.setattr(ollama, "check_pin", lambda name, digest: None)
    monkeypatch.setattr(ollama, "unload", lambda model: None)
    return call


def test_rejected_translation_is_marked_and_not_logged(french_call, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        ollama, "chat", lambda *a, **k: {"message": {"content": SECRET}}
    )  # echoes the source
    calls.run_stage("translate", french_call)
    out = load(french_call / "transcript.json")["segments"][0]
    assert "untranslated" in out["flags"] and out["en"] is None
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_crash_message_with_call_content_is_not_logged(french_call, monkeypatch, capsys) -> None:
    def explode(*args, **kwargs):
        raise ValueError(f"bad reply: {SECRET}")

    monkeypatch.setattr(ollama, "chat", explode)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["stage", "translate", str(french_call)])
    assert stopped.value.code == 1
    captured = capsys.readouterr()
    assert "ValueError at" in captured.err and SECRET not in captured.out + captured.err
    assert SECRET not in (french_call / "run.json").read_text()
