"""Call folders, run.json, stage staleness, prev/ copies, the per-call lock, VRAM waits and notifications.

Depends on: models.yaml (pins), ASCOLTA_DATA (required, the data folder), nvidia-smi, notify-send.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
STAGES = ("transcribe", "translate", "summarize", "ground")
MODEL_OF = {"transcribe": "transcriber", "translate": "translator", "summarize": "summarizer"}
OUTPUTS = {
    "transcribe": ("segments.json",),
    "translate": ("transcript.json", "transcript.md"),
    "summarize": ("summary.json",),
    "ground": ("summary.md",),
}
AUDIO_SUFFIXES = (".opus", ".ogg", ".wav", ".flac", ".mp3", ".m4a", ".webm")
VRAM_WAIT_S, VRAM_POLL_S = 1800, 30


class StageError(Exception):
    """A failure whose message is safe to log: it never contains call content."""


class VramTimeout(StageError):
    """The GPU stayed too full for the stage's whole wait."""


def data_dir() -> Path:
    value = os.environ.get("ASCOLTA_DATA")
    if not value:
        raise StageError(
            "ASCOLTA_DATA is not set; export it as the folder that holds the calls and profiles"
        )
    path = Path(value)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_models() -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = yaml.safe_load((REPO / "models.yaml").read_text())
    return models


def load_profile(person: str) -> tuple[dict[str, Any], bytes]:
    """The person's profile and its raw bytes (empty when there is no profile file)."""
    path = data_dir() / "people" / f"{person}.yaml"
    raw = path.read_bytes() if path.is_file() else b""
    profile = (yaml.safe_load(raw) if raw else None) or {}
    profile = {"name": person, "hotwords": [], "summary_notes": "", **profile}
    if not isinstance(profile["name"], str) or not isinstance(profile["summary_notes"], str):
        raise StageError(f"profile {person}: name and summary_notes must be text")
    if not isinstance(profile["hotwords"], list) or not all(
        isinstance(w, str) for w in profile["hotwords"]
    ):
        raise StageError(f"profile {person}: hotwords must be a list of names")
    return profile, raw


def write_atomic(path: Path, data: str | bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data.encode() if isinstance(data, str) else data)
    os.replace(tmp, path)


def write_json(path: Path, obj: Any) -> None:
    write_atomic(path, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def read_run(call: Path) -> dict[str, Any]:
    path = call / "run.json"
    run = json.loads(path.read_text()) if path.is_file() else {}
    run.setdefault("stages", {})
    return run


def update_run(call: Path, stage: str | None = None, **fields: Any) -> None:
    run = read_run(call)
    (run["stages"].setdefault(stage, {}) if stage else run).update(fields)
    write_json(call / "run.json", run)


def person_of(call: Path) -> str:
    return read_run(call).get("person") or call.name.split("_", 2)[-1]


def new_call(person: str) -> Path:
    call = data_dir() / f"{datetime.now():%Y-%m-%d_%H%M%S}_{person}"
    call.mkdir(mode=0o700)
    update_run(call, person=person)
    return call


def audio_file(call: Path) -> Path:
    found = [p for p in call.glob("audio.*") if p.suffix.lower() in AUDIO_SUFFIXES]
    if len(found) != 1:
        raise StageError(f"{call.name}: expected one audio.* file, found {len(found)}")
    return found[0]


def all_calls() -> list[Path]:
    return sorted(p for p in data_dir().iterdir() if p.is_dir() and any(p.glob("audio.*")))


def inputs_hash(call: Path, stage: str) -> str:
    """sha256 over everything the stage reads; a stage whose inputs changed is stale."""
    files = (
        [audio_file(call)]
        if stage == "transcribe"
        else {
            "translate": [call / "segments.json"],
            "summarize": [call / "transcript.json"],
            "ground": [call / "summary.json", call / "transcript.json"],
        }[stage]
    )
    h = hashlib.sha256()
    for path in files:
        h.update(path.name.encode() + hashlib.sha256(path.read_bytes()).digest())
    if stage in ("transcribe", "summarize"):
        h.update(b"profile" + hashlib.sha256(load_profile(person_of(call))[1]).digest())
    if stage in MODEL_OF:
        h.update(json.dumps(load_models()[MODEL_OF[stage]], sort_keys=True).encode())
    return h.hexdigest()


def is_done(call: Path, stage: str) -> bool:
    entry = read_run(call)["stages"].get(stage, {})
    if entry.get("status") != "done":
        return False
    try:
        return bool(entry.get("inputs_sha256") == inputs_hash(call, stage))
    except (FileNotFoundError, StageError):
        return False


def archive_outputs(call: Path, stage: str) -> None:
    """Copy the stage's existing outputs to prev/<stage>.<UTC timestamp>.<ext> before a re-run.

    A copy, not a move: the current output stays in place if the re-run fails.
    """
    stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    for path in (call / name for name in OUTPUTS[stage]):
        if path.is_file():
            (call / "prev").mkdir(mode=0o700, exist_ok=True)
            shutil.copy2(path, call / "prev" / f"{stage}.{stamp}{path.suffix}")


@contextmanager
def call_lock(call: Path) -> Iterator[None]:
    with open(call / ".lock", "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StageError(f"{call.name}: busy, another run holds its lock") from None
        yield


def notify(message: str) -> None:
    """Desktop notification plus a stderr line. Callers pass counts and names only, never call content."""
    print(f"ascolta: {message}", file=sys.stderr)
    if os.environ.get("ASCOLTA_NOTIFY", "1") != "0":
        subprocess.run(["notify-send", "Ascolta", message], check=False)


def free_vram_gb(count_ollama: bool) -> float:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    free = int(out.split()[0]) / 1024
    if count_ollama:
        from ascolta import ollama

        free += ollama.loaded_vram_gb()
    return free


def wait_for_vram(stage: str, label: str) -> None:
    need = load_models()[MODEL_OF[stage]]["vram_gb"]
    deadline, told = time.monotonic() + VRAM_WAIT_S, False
    while free_vram_gb(count_ollama=stage != "transcribe") < need:
        if time.monotonic() > deadline:
            raise VramTimeout(
                f"{label}: {stage} needs {need} GB of free VRAM; still short after 30 minutes"
            )
        if not told:
            notify(f"{label}: {stage} is waiting for {need} GB of free VRAM")
            told = True
        time.sleep(VRAM_POLL_S)


def run_stage(stage: str, call: Path) -> None:
    """Run one stage in this process under the call's lock and record the outcome in run.json."""
    module = importlib.import_module(f"ascolta.{stage}")
    with call_lock(call):
        try:
            digest = inputs_hash(call, stage)
        except FileNotFoundError as err:
            raise StageError(
                f"{call.name}: {stage} input {Path(err.filename).name} is missing"
            ) from None
        if stage in MODEL_OF:
            try:
                wait_for_vram(stage, call.name)
            except VramTimeout as err:
                update_run(call, stage, status="waiting-timeout", error=str(err), finished=now())
                raise
        archive_outputs(call, stage)
        update_run(call, stage, status="running", started=now(), error=None)
        try:
            info = module.run(call)
        except StageError as err:
            update_run(call, stage, status="failed", error=str(err), finished=now())
            raise
        except Exception as err:
            update_run(call, stage, status="failed", error=safe_trace(err), finished=now())
            raise
        update_run(call, stage, status="done", inputs_sha256=digest, finished=now(), **info)
    counts = ", ".join(f"{v} {k}" for k, v in info.get("counts", {}).items())
    print(f"ascolta: {call.name}: {stage} done ({counts})", file=sys.stderr)


def safe_trace(err: BaseException) -> str:
    """Exception type and code locations only: exception messages can carry call content."""
    frames = traceback.extract_tb(err.__traceback__)[-4:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(err).__name__} at {where}"


def process(call: Path) -> bool:
    """Run every stale or missing stage in order, each in its own process; notify the outcome."""
    label = f"{person_of(call)} {call.name[:15]}"
    for stage in STAGES:
        if is_done(call, stage):
            continue
        result = subprocess.run(
            [sys.executable, "-m", "ascolta", "stage", stage, str(call)], check=False
        )
        if result.returncode != 0:
            notify(f"{label}: {stage} failed; it stays pending (ascolta process --pending)")
            return False
    counts = read_run(call)["stages"]["ground"].get("counts", {})
    notify(f"{label}: {counts.get('action items', 0)} action items, {counts.get('⚠', 0)} ⚠")
    return True
