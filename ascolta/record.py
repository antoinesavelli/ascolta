"""Capture: my mic on the left channel, the default sink's monitor on the right, encoded as 64 kbps Opus.

Depends on: pw-record and pw-link (PipeWire), pactl, PyAV (libopus), notify-send.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Any

import av
import numpy as np

from ascolta.calls import (
    STAGES,
    StageError,
    all_calls,
    data_dir,
    is_done,
    new_call,
    notify,
    now,
    update_run,
)

RATE, FRAME_BYTES = 48000, 4  # s16 stereo
READ_BYTES = RATE * FRAME_BYTES // 10  # 0.1 s
MIC_PORT = "capture_FL"  # the USB mic is mono: both ports carry the voice (checked in phase 0)
PEAK_FLOOR = int(32768 * 10 ** (-60 / 20))  # −60 dBFS
ZERO_S, QUIET_S, SINK_POLL_S = 5, 180, 10


def _out(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def pid_file() -> Path:
    return data_dir() / ".recording.pid"


def _start_time(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def live_recording() -> int | None:
    """pw-record's PID if a recording is running; a stale PID file is removed with a notice."""
    path = pid_file()
    if not path.is_file():
        return None
    pid_text, start = path.read_text().split()
    pid = int(pid_text)
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        cmdline = b""
    if cmdline.startswith(b"pw-record") and _start_time(pid) == start:
        return pid
    path.unlink()
    print("ascolta: removed a stale recording PID file", file=sys.stderr)
    return None


def stop() -> None:
    pid = live_recording()
    if pid is None:
        raise StageError("no recording is running")
    os.kill(pid, signal.SIGINT)


def start_warnings(sink: str) -> list[str]:
    sinks = json.loads(_out("pactl", "--format=json", "list", "sinks"))
    info = next((s for s in sinks if s["name"] == sink), None)
    warnings = []
    if info is None or info["properties"].get("device.icon_name") != "audio-headphones":
        warnings.append(
            "the default output is not headphones: the remote voice will bleed into the mic"
        )
    if info is not None:
        inputs = json.loads(_out("pactl", "--format=json", "list", "sink-inputs"))
        apps = sorted(
            {
                i["properties"].get("application.name", "?")
                for i in inputs
                if i["sink"] == info["index"] and not i.get("corked")
            }
        )
        if apps:
            warnings.append(
                f"playing to the default output: {', '.join(apps)}; the right channel records all of it"
            )
    return warnings


def _wait_ports(node: str) -> None:
    for _ in range(50):
        if f"{node}:input_FL" in _out("pw-link", "-i").splitlines():
            return
        time.sleep(0.1)
    raise StageError("pw-record's input ports never appeared")


def _link(src: str, dst: str) -> None:
    subprocess.run(["pw-link", src, dst], check=True, capture_output=True)


class LevelWatch:
    """Notifies once per episode when a channel goes digitally silent (5 s) or quiet (3 minutes)."""

    def __init__(self) -> None:
        self.zero, self.quiet = [0.0, 0.0], [0.0, 0.0]
        self.alerted: list[set[str]] = [set(), set()]

    def feed(self, samples: np.ndarray) -> None:
        seconds = len(samples) / RATE
        for ch, name in enumerate(("mic (left)", "call (right)")):
            peak = int(np.abs(samples[:, ch].astype(np.int32)).max(initial=0))
            self.zero[ch] = self.zero[ch] + seconds if peak == 0 else 0.0
            self.quiet[ch] = self.quiet[ch] + seconds if peak < PEAK_FLOOR else 0.0
            self._alert(
                ch,
                "zero",
                self.zero[ch] >= ZERO_S,
                f"{name} is muted or unlinked (5 s of digital silence)",
            )
            self._alert(
                ch, "quiet", self.quiet[ch] >= QUIET_S, f"{name} has been silent for 3 minutes"
            )

    def _alert(self, ch: int, kind: str, active: bool, message: str) -> None:
        if active and kind not in self.alerted[ch]:
            notify(message)
            self.alerted[ch].add(kind)
        elif not active:
            self.alerted[ch].discard(kind)


def _follow_sink(sink: str, node: str, capture: dict[str, Any]) -> str:
    current = _out("pactl", "get-default-sink")
    if current == sink:
        return sink
    subprocess.run(
        ["pw-link", "-d", f"{sink}:monitor_FL", f"{node}:input_FR"],
        check=False,
        capture_output=True,
    )
    _link(f"{current}:monitor_FL", f"{node}:input_FR")
    capture["sink_switches"].append({"at": now(), "sink": current})
    notify("the output device changed; the recording follows it")
    return current


def _encode(
    stream: IO[bytes], path: Path, capture: dict[str, Any], node: str, follow: bool
) -> None:
    container = av.open(str(path), "w", format="ogg")
    out = container.add_stream("libopus", rate=RATE, layout="stereo")
    out.bit_rate = 64000
    watch, sink, polled, pts = LevelWatch(), capture["sink"], time.monotonic(), 0
    try:
        while chunk := stream.read(READ_BYTES):
            samples = np.frombuffer(
                chunk[: len(chunk) - len(chunk) % FRAME_BYTES], dtype=np.int16
            ).reshape(-1, 2)
            frame = av.AudioFrame.from_ndarray(
                samples.reshape(1, -1), format="s16", layout="stereo"
            )
            frame.sample_rate, frame.pts = RATE, pts
            pts += len(samples)
            for packet in out.encode(frame):
                container.mux(packet)
            watch.feed(samples)
            if follow and time.monotonic() - polled >= SINK_POLL_S:
                sink, polled = _follow_sink(sink, node, capture), time.monotonic()
        for packet in out.encode(None):
            container.mux(packet)
    finally:
        container.close()


def record(person: str, mic: str | None = None, sink: str | None = None) -> Path:
    """Record until Ctrl+C or `ascolta stop`; returns the new call folder.

    `mic` (a full port name) and `sink` default to the system defaults; only a defaulted sink is followed.
    """
    if live_recording():
        raise StageError("a recording is already running (ascolta stop ends it)")
    pending = [c for c in all_calls() if not all(is_done(c, s) for s in STAGES)]
    if pending:
        print(
            f"ascolta: {len(pending)} call(s) have unfinished stages (ascolta process --pending)",
            file=sys.stderr,
        )
    follow = sink is None
    sink = sink or _out("pactl", "get-default-sink")
    mic = mic or f"{_out('pactl', 'get-default-source')}:{MIC_PORT}"
    warnings = start_warnings(sink)
    for warning in warnings:
        notify(warning)
    call = new_call(person)
    node = f"ascolta-{os.getpid()}"
    rec = subprocess.Popen(
        [
            "pw-record",
            "--target",
            "0",
            "--channels",
            "2",
            "--rate",
            str(RATE),
            "--format",
            "s16",
            "--raw",
            "-P",
            f'{{ node.name = "{node}" }}',
            "-",
        ],
        stdout=subprocess.PIPE,
    )
    signal.signal(
        signal.SIGINT, signal.SIG_IGN
    )  # Ctrl+C stops pw-record; this process drains and finishes
    pid_file().write_text(f"{rec.pid} {_start_time(rec.pid)}\n")
    capture = {
        "mic": mic,
        "sink": sink,
        "started": now(),
        "warnings": warnings,
        "sink_switches": [],
    }
    try:
        _wait_ports(node)
        _link(mic, f"{node}:input_FL")
        _link(f"{sink}:monitor_FL", f"{node}:input_FR")
        update_run(call, capture=capture)
        print(
            f"ascolta: recording {call.name}; stop with Ctrl+C or `ascolta stop`", file=sys.stderr
        )
        assert rec.stdout is not None
        _encode(rec.stdout, call / "audio.opus", capture, node, follow)
    finally:
        if rec.poll() is None:
            rec.send_signal(signal.SIGINT)
        rec.wait()
        pid_file().unlink(missing_ok=True)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        capture["ended"] = now()
        update_run(call, capture=capture)
    return call
