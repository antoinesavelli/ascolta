"""Test 2: speech on the left and noise on the right give only `me` segments, no invented `remote` lines."""

from __future__ import annotations

import numpy as np
import pytest
from conftest import cli, load, mono, write_stereo


@pytest.mark.gpu
def test_noise_channel_produces_no_remote_lines(tmp_path) -> None:
    from ascolta.calls import new_call

    speech = mono(
        "stereo_diarization.wav"
    )  # decode_audio downmixes; both speakers end up on the left
    noise = np.random.default_rng(0).standard_normal(len(speech)).astype(np.float32) * 0.01
    call = new_call("tester")
    write_stereo(call / "audio.wav", speech, noise)
    result = cli("stage", "transcribe", str(call))
    assert result.returncode == 0, result.stderr
    segments = load(call / "segments.json")["segments"]
    assert segments, "no speech found on the left channel"
    assert {s["speaker"] for s in segments} == {"me"}
