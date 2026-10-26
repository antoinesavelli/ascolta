# The loop here

The doctrine loop (AGENTS.md core block) with what is specific to ascolta.

## OBSERVE

- Read `docs/STATUS.md` and the `docs/DESIGN.md` section you are touching.
- `git status --short` and `git log --oneline -10` first; another session may be mid-edit.
- Never observe call data: only public clips (`ASCOLTA_CLIPS`) and synthetic audio.

## VERIFY: Definition of Done

Run each yourself; one that cannot run is reported as not run. The tests marked `gpu`, `ollama` and
`pipewire` need this workstation outside the Claude sandbox (the sandbox blocks the GPU, Ollama and
PipeWire).

1. `uv run pytest -q` passes; with `ASCOLTA_CLIPS` set to the public clips folder, none of the clip tests
   is skipped. New behavior has a test that pins it and its failure mode.
2. `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` are clean.
3. Each module's docstring is one line plus an accurate `Depends on:` line.
4. Docs current: `README.md` map, `docs/STATUS.md`, a `docs/DECISIONS.md` row for a new decision or reversal.
5. `git config core.hooksPath` reads `.githooks`.
6. Committed by explicit path (`git add <paths>`, `git diff --cached` read in full). Creating the remote and
   pushing are ask-first.

## CLOSE

What changed, what was verified and how, what is next; `docs/STATUS.md` updated in the same commit.
