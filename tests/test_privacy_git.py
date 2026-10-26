"""Test 4: call data and audio never enter git, the hooks are live and work, and ASCOLTA_DATA is required."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import REPO

AUDIO = (".opus", ".ogg", ".wav", ".flac", ".mp3", ".m4a", ".webm")


def git(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def test_no_call_data_or_audio_is_tracked() -> None:
    tracked = git("ls-files").stdout.splitlines()
    assert not [p for p in tracked if p.startswith("transcripts/") or p.lower().endswith(AUDIO)]
    assert git("check-ignore", "-q", "transcripts/2026-01-01_000000_x/audio.opus").returncode == 0


def test_hooks_path_is_set() -> None:
    assert git("config", "core.hooksPath").stdout.strip() == ".githooks", (
        "run once: git config core.hooksPath .githooks"
    )


def test_pre_commit_hook_rejects_audio_and_call_data(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "transcripts").mkdir(parents=True)
    git("init", "-q", cwd=repo)
    shutil.copytree(REPO / ".githooks", repo / ".githooks")
    git("config", "core.hooksPath", ".githooks", cwd=repo)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for bad in ("dummy.OPUS", "clip.wav", "transcripts/notes.txt", "transcripts/x.json"):
        (repo / bad).parent.mkdir(parents=True, exist_ok=True)
        (repo / bad).write_text("x")
        git("add", bad, cwd=repo)
        result = subprocess.run(
            ["git", "commit", "-qm", "t"], cwd=repo, capture_output=True, text=True, env=env
        )
        assert result.returncode != 0 and "refusing" in result.stderr, bad
        git("reset", "-q", cwd=repo)
    (repo / "ok.txt").write_text("x")
    git("add", "ok.txt", cwd=repo)
    assert subprocess.run(["git", "commit", "-qm", "t"], cwd=repo, env=env).returncode == 0


def test_data_folder_follows_ascolta_data(data: Path) -> None:
    from ascolta.calls import data_dir

    assert data_dir() == data and oct(data.stat().st_mode & 0o777) == "0o700"


def test_unset_ascolta_data_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    from ascolta.calls import StageError, data_dir

    monkeypatch.delenv("ASCOLTA_DATA")
    with pytest.raises(StageError, match="ASCOLTA_DATA"):
        data_dir()
    result = subprocess.run(
        [sys.executable, "-m", "ascolta", "process", "--pending"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={k: v for k, v in os.environ.items() if k != "ASCOLTA_DATA"},
    )
    assert result.returncode == 1 and "ASCOLTA_DATA" in result.stderr
