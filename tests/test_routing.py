"""Test 6: the recorder puts the mic on the left and the call (a sink's monitor) on the right.

Two temporary `pw-loopback` virtual sinks stand in for the call and the mic, at the lowest priority so
neither can become the default output; nothing touches the real mic.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator

import numpy as np
import pytest
from conftest import REPO, cli

CALL_SINK, QUIET_SINK = "ascolta-test-call", "ascolta-test-quiet"


def virtual_sink(name: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            "pw-loopback",
            f"--capture-props=media.class=Audio/Sink node.name={name} audio.position=[FL FR] priority.session=1 "
            "priority.driver=1",
            f"--playback-props=node.name={name}-out node.passive=true audio.position=[FL FR] target.object=0 "
            "node.dont-reconnect=true",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for(predicate, what: str, seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        time.sleep(0.1)


@pytest.fixture
def sinks() -> Iterator[None]:
    procs = [virtual_sink(CALL_SINK), virtual_sink(QUIET_SINK)]
    try:
        wait_for(
            lambda: (
                f"{QUIET_SINK}:monitor_FL"
                in subprocess.run(["pw-link", "-o"], capture_output=True, text=True).stdout
            ),
            "the virtual sinks",
        )
        yield
    finally:
        for proc in procs:
            proc.terminate()
            proc.wait()


@pytest.mark.pipewire
def test_tone_on_the_call_sink_lands_on_the_right_only(sinks, data) -> None:
    code = (
        f"from ascolta.record import record; print(record('tester', mic='{QUIET_SINK}:monitor_FL', "
        f"sink='{CALL_SINK}'))"
    )
    recorder = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_for(lambda: (data / ".recording.pid").is_file(), "the recording to start")
    time.sleep(0.5)
    tone = (0.05 * 32767 * np.sin(2 * np.pi * 440 * np.arange(48000 * 2) / 48000)).astype(np.int16)
    subprocess.run(
        [
            "pw-play",
            "--target",
            CALL_SINK,
            "--channels",
            "2",
            "--rate",
            "48000",
            "--format",
            "s16",
            "--raw",
            "-",
        ],
        input=np.repeat(tone, 2).tobytes(),
        check=True,
        timeout=10,
    )
    assert cli("stop").returncode == 0
    out, err = recorder.communicate(timeout=20)
    assert recorder.returncode == 0, err
    assert not (data / ".recording.pid").exists()
    from faster_whisper import decode_audio

    left, right = decode_audio(out.strip().splitlines()[-1] + "/audio.opus", split_stereo=True)
    rms = [20 * np.log10(max(float(np.sqrt(np.mean(ch**2))), 1e-9)) for ch in (left, right)]
    assert rms[0] < -60, f"left channel is not silent: {rms[0]:.1f} dBFS"
    assert -40 < rms[1] < -20, f"right channel doesn't carry the tone: {rms[1]:.1f} dBFS"
