"""Test 7: a changed input makes the downstream stage stale, a wrong model pin stops the stage, and a
re-run keeps the old output in prev/."""

from __future__ import annotations

import json

import pytest
from conftest import fake_call, load, segment

from ascolta import calls, ollama, translate


def mark_done(call, stage: str) -> None:
    calls.update_run(call, stage, status="done", inputs_sha256=calls.inputs_hash(call, stage))


def test_editing_the_transcript_makes_the_summary_stale(data) -> None:
    call = fake_call(data, [segment(5, "I will call the bank on Monday morning.")])
    mark_done(call, "summarize")
    assert calls.is_done(call, "summarize")
    transcript = load(call / "transcript.json")
    transcript["segments"].append(segment(9, "And then the plumber."))
    calls.write_json(call / "transcript.json", transcript)
    assert not calls.is_done(call, "summarize")


def test_profile_change_makes_the_summary_stale(data) -> None:
    call = fake_call(data, [segment(5, "Hello there.")])
    mark_done(call, "summarize")
    (data / "people").mkdir()
    (data / "people" / "tester.yaml").write_text("summary_notes: my colleague\n")
    assert not calls.is_done(call, "summarize")


@pytest.mark.ollama
def test_wrong_digest_stops_the_ollama_stage(data, monkeypatch) -> None:
    call = fake_call(data, [])
    calls.write_json(
        call / "segments.json",
        {"duration_s": 9, "segments": [segment(1, "Je vais appeler la banque lundi.", lang="fr")]},
    )
    models = calls.load_models()
    models["translator"]["digest"] = "0" * 64
    monkeypatch.setattr(translate, "load_models", lambda: models)
    monkeypatch.setattr(calls, "wait_for_vram", lambda stage, label: None)
    with pytest.raises(calls.StageError, match="does not match the pin"):
        calls.run_stage("translate", call)
    assert load(call / "run.json")["stages"]["translate"]["status"] == "failed"
    assert (
        not (call / "transcript.json").read_text().count("Je vais")
    )  # nothing was written over it


@pytest.fixture
def summarized_call(data, monkeypatch):
    call = fake_call(data, [segment(5, "I will call the bank on Monday morning.")])
    calls.write_json(call / "summary.json", {"summary": [], "action_items": []})
    monkeypatch.setattr(calls, "wait_for_vram", lambda stage, label: None)
    monkeypatch.setattr(ollama, "check_pin", lambda name, digest: None)
    return call


def test_a_rerun_summarize_keeps_the_old_summary(summarized_call, monkeypatch) -> None:
    new = {
        "summary": [{"text": "A bank call.", "ts": "00:05", "quote": "I will call the bank on"}],
        "action_items": [],
    }
    reply = {"message": {"content": json.dumps(new)}, "done_reason": "stop"}
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: reply)
    calls.run_stage("summarize", summarized_call)
    assert load(summarized_call / "summary.json") == new
    kept = list((summarized_call / "prev").glob("summarize.*.json"))
    assert len(kept) == 1 and load(kept[0]) == {"summary": [], "action_items": []}


def test_a_failed_rerun_leaves_the_summary_in_place(summarized_call, monkeypatch) -> None:
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: {"message": {"content": "not json"}})
    with pytest.raises(calls.StageError, match="invalid JSON"):
        calls.run_stage("summarize", summarized_call)
    assert load(summarized_call / "summary.json") == {"summary": [], "action_items": []}
