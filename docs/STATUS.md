# Ascolta: status

Single owner of dynamic status. Edit in place; nothing else restates it.

**Phase: 0 exit not met; the phase 1 pipeline is built** (2026-10-25). The repo has been brought onto the
corsu standard (`docs/agents/NEW_REPO.md` in system-library): uv lock, ruff, mypy `--strict`, hooks, CI,
and a public-ready layout. No remote exists and nothing has been pushed (D-009: creating it is the owner's
call).

**Exit:** phase 2 done (winners pinned in `models.yaml`, older calls re-processed).

## History carried over from PLAN.md

**Status:** design settled 2026-10-23, revised the same day after a design review and machine checks,
and again 2026-10-24, including the fixes from a blind re-grade (C−). Built 2026-10-24: phase 0 skeleton
and the phase 1 pipeline with tests 1–8: all 29 pass outside the sandbox; inside it 22 pass, because tests
2, 3, 5, 6 and 7 need the GPU, Ollama or PipeWire. Applied 2026-10-24 with your approval: `core.hooksPath`, the
user-level Claude and opencode denies, the `AGENTS_CONSUMERS` entry and the three model-routing entries
(`check.sh agents` and `check_model_config_sync.py` pass). Phase 0 checks run 2026-10-24 with you present:
the capture self-test passes, with one design finding (Capture, Test results); the agent-access proof
found open routes (Privacy, "Found in phase 0"); on 2026-10-25 you closed the terminal-panel route and
opencode's default agent. **Phase 0 exit not met.** Open, all yours to decide: the one agent-access route that
remains (below), the right-channel silence alert, and whether sandboxed agents should reach
the GPU and Ollama (they can't today). Still unchecked: the translator's VRAM at `num_ctx` 4096.

## Open items (carried over from PLAN.md, 2026-10-25)

**Found in phase 0 (2026-10-24).** Every route inside the sandbox failed on the dummy:
the Read and Write tools, a symlink, `cat`, `grep -r`, `python -I` (also via `/proc/self/root`), a retry
with the sandbox flag off, and `read_terminal`. A Claude session started in `~` was refused both Read and
`cat`. Open:
- Closed 2026-10-25: `mcp__terminal__run_in_terminal` ran in the app's terminal panel, outside the sandbox
  and the deny rules (it wrote a file into `transcripts/` and copied a match count to a path the Read tool
  can open), and `mcp__terminal__stop_terminal_tab` returned a tab's last screen lines. The repo now denies
  `mcp__terminal`; all three tools answer "permission denied" (checked in a session with the new setting).
- Closed 2026-10-25 for opencode's default agent: the top-level `external_directory` deny (layer 2).
- **Still open:** some opencode agents are not held by the per-agent read deny in the config file; the cause is
  unknown. Those agents are only ever run from another project, and `AGENTS.md` forbids running opencode in or
  above the folder that holds the call data.
- Two routes depend on what you do yourself, in the app's browser pane and in commands you run outside the
  sandbox: open no call files in either.

## Description and topics (drafts for the owner's approval)

- **GitHub About** (= `pyproject.toml` `description`): see `pyproject.toml`.
- **Topics:** `speech-to-text`, `faster-whisper`, `ollama`, `local-llm`, `pipewire`, `python`.

## Build order

- **Who builds (2026-10-24):** a Claude Opus session acting as delegator. It makes the judgment calls and checks every
  change itself; small mechanical edits go to the local coding model named in `model-routing.yaml`
  (today `devstral-small-2:24b`) through the `local-model-subagent` skill, each unit in a throwaway
  sandbox outside the call-data folder. On 2026-10-24 `opencode run` hung after `init` twice (no session, no model
  load), so the build was written by the Opus session alone.
- **Phase 0 — guards and capture, before any real call:**
  - **Skeleton:**
    - `git init`, `.gitignore`, `.githooks/`, a uv venv.
    - A symlink `~/.local/bin/ascolta` → `.venv/bin/ascolta`, so the command always runs in the repo's own
      venv. Since 2026-10-25 it is a wrapper script that exports `ASCOLTA_DATA` and `ASCOLTA_CLIPS`, then runs
      `corsu/ascolta/.venv/bin/ascolta`.
    - `models.yaml` as above.
    - `.claude/settings.json` (Privacy, layer 1).
    - `AGENTS.md` with the doctrine-core block, identical to `AGENT_DOCTRINE_CORE.md` between the
      `doctrine-core` markers, and a `CLAUDE.md` that is exactly `@AGENTS.md`.
  - **You apply or approve** (they change config outside this repo):
    - `core.hooksPath`.
    - The user-level deny rules (Claude and opencode).
    - Adding the old call folder to `AGENTS_CONSUMERS` in system-library's `tools/check.sh` (now
      `corsu/ascolta`).
    - The three model-routing entries.
  - **Agent-access proof:** Privacy, layer 6.
  - **Capture self-test:** play public audio through the headphone sink while you talk.
    - Your voice shows on the left and the audio on the right.
    - A muted mic triggers the notification.
    - Switching output mid-call relinks.
    - Ctrl+C and `ascolta stop` both leave a playable file.
  - **Unverified items, checked 2026-10-24:**
    - Which mic port carries your voice: both (a mono mic); `capture_FL` is right.
    - Linking `monitor_FL` alone: works (Capture, phase 0 self-test).
    - CUDA/cuDNN in the venv: work (tests 3 and 5 pass, with `device="cuda"`); `pw-loopback` monitor ports
      for test 6: work.
    - The translator's VRAM at `num_ctx` 4096: not checked yet.
    - Whether the repo's sandbox lets a Claude session reach the GPU and Ollama: it doesn't. Both
      `/dev/nvidia*` and `localhost:11434` are unreachable, so agents can't run tests 2, 3, 5, 6 or 7 in this
      repo; the fix is yours to decide.
  - **Exit:** all of the above pass, and `tools/check.sh agents` and `check_model_config_sync.py` pass.
- **Phase 1 — the pipeline with provisional models, plus tests 1–8.**
  - **Exit:** test 3 passes with a grounding report. Then the first real call.
- **Phase 2 — the bake-off:**
  1. The one-meeting trial and GPU-hour estimate.
  2. The full run and `models.proposed.yaml`.
  3. The 3-call check, then you apply it.
  4. Re-process older calls, one first.
