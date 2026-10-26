"""Shared fixtures: every test runs against a temporary ASCOLTA_DATA, never `transcripts/`."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data"
    monkeypatch.setenv("ASCOLTA_DATA", str(path))
    monkeypatch.setenv("ASCOLTA_NOTIFY", "0")
    return path


def clip(name: str) -> Path:
    """A public test clip from the folder ASCOLTA_CLIPS names; skip when it is unset."""
    folder = os.environ.get("ASCOLTA_CLIPS")
    if not folder:
        pytest.skip("ASCOLTA_CLIPS is not set (the folder that holds the public test clips)")
    path = Path(folder) / name
    if not path.is_file():
        pytest.fail(f"public test clip {name} is missing from ASCOLTA_CLIPS ({folder})")
    return path


def mono(name: str) -> np.ndarray:
    from faster_whisper import decode_audio

    return decode_audio(str(clip(name)), sampling_rate=16000)


def write_stereo(path: Path, left: np.ndarray, right: np.ndarray, rate: int = 16000) -> Path:
    n = max(len(left), len(right))
    both = np.zeros((n, 2), dtype=np.float32)
    both[: len(left), 0], both[: len(right), 1] = left, right
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(both, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    data = os.environ.get("ASCOLTA_DATA", "")
    assert data and not Path(data).resolve().is_relative_to(REPO), (
        "tests must run on a temporary ASCOLTA_DATA"
    )
    return subprocess.run(
        [sys.executable, "-m", "ascolta", *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=os.environ.copy(),
    )


def fake_call(data: Path, segments: list[dict], duration: float = 120.0) -> Path:
    """A call folder holding a transcript.json, for stages that don't need audio."""
    from ascolta.calls import new_call, write_json

    call = new_call("tester")
    write_json(call / "transcript.json", {"duration_s": duration, "segments": segments})
    return call


def segment(
    start: float, text: str, en: str | None = None, flags: list[str] | None = None, **extra
) -> dict:
    return {
        "start": start,
        "end": start + 4,
        "speaker": "remote",
        "lang": "en",
        "lang_prob": 0.99,
        "lang_mass": 0.99,
        "text": text,
        "en": en,
        "flags": flags or [],
        **extra,
    }


def load(path: Path) -> dict:
    return json.loads(path.read_text())
