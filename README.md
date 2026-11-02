# ascolta

Ascolta records a call on Linux (PipeWire: my microphone on the left channel, the call audio on the right),
transcribes each channel with faster-whisper, translates non-English segments into English and summarizes
the call with local Ollama models, then checks in code that every quote the summary cites exists in the
transcript near its timestamp. The pipeline calls only local models, no hosted API. It is used by one person
on one workstation, with no outside users, and it was built by directing AI coding agents and accepting their
work on tests and checks. Status: the pipeline is built; the bake-off that picks the final models has not
run (`docs/STATUS.md`).

Agent instructions: `AGENTS.md`. Spec: `docs/DESIGN.md`. Decisions: `docs/DECISIONS.md`. Status: `docs/STATUS.md`.

## Use

```
uv sync
git config core.hooksPath .githooks        # once per clone
export ASCOLTA_DATA=<folder for calls and profiles>   # required, no default
uv run ascolta record <person>             # Ctrl+C or `ascolta stop` ends it, then it processes
uv run ascolta process <call-dir | audio file>
uv run ascolta process --pending
```

Tests: `uv run pytest -q` skips the tests that need public audio clips. Point `ASCOLTA_CLIPS` at the folder
holding `jfk.flac`, `multilingual.mp3` and `stereo_diarization.wav` to run them. The tests
marked `gpu`, `ollama` and `pipewire` need a CUDA GPU, a running Ollama with the pinned models, and a PipeWire
session.

## Area map

| Path | What it is |
|---|---|
| `AGENTS.md` · `CLAUDE.md` | Agent instructions · `@AGENTS.md` only |
| `docs/agents/` | Agent topic files: `LOOP.md` (loop, Definition of Done), `CONVENTIONS.md` |
| `docs/DESIGN.md` · `DECISIONS.md` · `STATUS.md` | Spec · decisions and parked work · current status |
| `ascolta/` | The package: `cli.py` (commands), `calls.py` (call folders, `run.json`, staleness, `prev/` copies, locks), `record.py` (capture), `transcribe.py`, `translate.py`, `summarize.py`, `ground.py` (quote check), `ollama.py` (local client) |
| `models.yaml` | Model names, pins and VRAM needs: the only place a model name appears |
| `typings/` | Hand-written type stubs for the `faster_whisper` names ascolta uses (the library ships none), found through `mypy_path` |
| `tests/` | Tests; call data is never used, only public or synthetic audio |
| `pyproject.toml` · `uv.lock` | Package and tool config · locked dependencies |
| `.githooks/` | `pre-commit` refuses credentials and `.githooks/refuse` paths (transcripts, audio); `pre-push` runs gitleaks on full history |
| `.claude/settings.json` | Claude Code project settings: sandbox on, terminal server denied. The untracked `.claude/settings.local.json` denies transcript Read/Edit |
| `.github/workflows/ci.yml` | `uv sync --locked`, ruff, ruff format, mypy, pytest (workstation-only tests deselected) |
| `LICENSE` | MIT |
