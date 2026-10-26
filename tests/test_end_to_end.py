"""Test 3: one public 2-person clip runs through every stage. Test 4 (logs): its output carries no transcript text."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
from conftest import cli, load, mono, write_stereo

from ascolta.calls import STAGES

SEGMENT_KEYS = {"start", "end", "speaker", "lang", "lang_prob", "lang_mass", "text", "en", "flags"}


@pytest.fixture(scope="module")
def pipeline(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    """JFK on the left (me), then a second speaker on the right (remote); the whole pipeline, once.

    Module-scoped, so it runs before the per-test ASCOLTA_DATA fixture and must set its own.
    """
    with pytest.MonkeyPatch.context() as env:
        env.setenv("ASCOLTA_DATA", str(tmp_path_factory.mktemp("data")))
        env.setenv("ASCOLTA_NOTIFY", "0")
        return _run_pipeline(tmp_path_factory)


def _run_pipeline(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    jfk = mono("jfk.flac")
    remote = np.concatenate(
        [np.zeros(len(jfk) + 16000, dtype=np.float32), mono("stereo_diarization.wav")]
    )
    clip = write_stereo(tmp_path_factory.mktemp("clip") / "two_person.wav", jfk, remote)
    result = cli("process", str(clip), "--person", "tester")
    from ascolta.calls import all_calls

    calls = all_calls()
    assert len(calls) == 1, result.stderr
    return calls[0], result


@pytest.mark.gpu
@pytest.mark.ollama
def test_every_stage_runs_and_files_match_the_schema(pipeline) -> None:
    call, result = pipeline
    assert result.returncode == 0, result.stderr
    run = load(call / "run.json")
    for stage in STAGES:
        entry = run["stages"][stage]
        assert entry["status"] == "done" and len(entry["inputs_sha256"]) == 64, stage
    for stage in ("transcribe", "translate", "summarize"):
        assert run["stages"][stage]["pin"], stage
    transcript = load(call / "transcript.json")
    assert transcript["duration_s"] > 0
    assert transcript["segments"] and all(set(s) == SEGMENT_KEYS for s in transcript["segments"])
    assert {s["speaker"] for s in transcript["segments"]} == {"me", "remote"}
    summary = load(call / "summary.json")
    assert set(summary) == {"summary", "action_items"}
    report = (call / "summary.md").read_text()
    print(report)  # the grounding report, shown with `pytest -s`
    assert "## Summary" in report and "## Action items" in report


@pytest.mark.gpu
@pytest.mark.ollama
def test_logs_carry_no_transcript_text(pipeline) -> None:
    call, result = pipeline
    output = (result.stdout + result.stderr).casefold()
    texts = [s["text"] for s in load(call / "transcript.json")["segments"]]
    texts += [
        i["quote"] for key in ("summary", "action_items") for i in load(call / "summary.json")[key]
    ]
    leaks = [t for t in texts if len(t) > 12 and t.casefold() in output]
    assert not leaks
