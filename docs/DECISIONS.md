# Ascolta: decisions

One row per decision; a reversal edits the row's Status and adds a new row. Rows D-001 to D-008 are carried
over from `PLAN.md` ("Decisions owned by the user" and the decisions made inside its sections). "You" in a
carried-over row is the owner.

| ID | Date | Decision | Why | Status |
|---|---|---|---|---|
| D-001 | 2026-10-23 | **Data lives inside the repo folder** in `transcripts/`: gitignored, `chmod 700`, not encrypted (the ext4 partition is unencrypted; swap is encrypted). | Chosen against the recommendation to keep data outside. Offered but not adopted: fscrypt on `transcripts/` alone would protect a stolen disk, though not against agents (parked below). | Superseded 2026-10-25 by D-010 and D-011: the repo moved to `corsu/ascolta` and the data stays in its old folder on this workstation, outside it. |
| D-002 | 2026-10-23 | **Backup:** `transcripts/` stays in the owner's nightly encrypted backup. The whole folder, `.venv` and `bakeoff/data/` included, stays in the backup (decided 2026-10-24). "Local" means no paid-API agent ever sees call content. | The backup is encrypted and kept off the machine, so calls leave it as ciphertext. A deleted call stays in the archives until they are pruned. | Active. The earlier clause "Local means: no git remote" is reversed by D-009. |
| D-003 | 2026-10-23 | **Translation:** non-English segments get an English line beneath; the original is kept. No interpreter role. | | Active |
| D-004 | 2026-10-23 | **Consent:** nothing is tracked or enforced, against the recommendation. Optional habit, no code: say "I'm recording this so I don't forget" at the start of the call. | Known risk: places where every party must consent (e.g. France, Florida, California) and work calls. | Active |
| D-005 | 2026-10-23 | **Git: local only, never a remote.** | Part of what "local" meant in D-002 as first written. | Reversed 2026-10-25 by D-009. |
| D-006 | 2026-10-24 | **Agent boundary: layered rules, with the gap stated** (`docs/DESIGN.md`, Privacy and agent access). | Chosen over turning Claude's sandbox on for every session, and over giving `transcripts/` its own Unix user. | Active |
| D-007 | 2026-10-24 | **Capture Plan B:** if the `pw-link` routing fails in phase 0, record two mono files instead, `mic.opus` and `remote.opus`, each from its own `pw-record`, with each start time in `run.json`. | The routing passed its phase 0 self-test, so the plan is not needed. | Not triggered |
| D-008 | 2026-10-24 | **Accepted known gap:** scripts run by Claude sessions started outside this repo (or that `/cd` out of it) and opencode's bash tool have no hard block. | The two sandbox settings close the sandbox's own escape routes; the rest stays a layered-rules gap. | Active |
| D-009 | 2026-10-25 | **ascolta goes public** on `antoinesavelli` under MIT. The no-remote test assertion, the always-fail `pre-push` and the `git push` / `git remote add` denies are removed; the pre-commit refusal of transcripts and audio stays, as `.githooks/refuse` globs; `pre-push` becomes the gitleaks scan. Creating the remote and every push stay the owner's call. | Corsu migration decisions 9 and 11 (owner, 2026-10-25). The call data was never tracked: it is gitignored and refused by the pre-commit hook. | Active |
| D-010 | 2026-10-25 | **`ASCOLTA_DATA` is required.** No default path in code; unset, the pipeline fails loud with an error naming the variable. Test clips come from `ASCOLTA_CLIPS` and the tests that need them skip when it is unset. | A public repo cannot carry a personal default path. | Active |
| D-011 | 2026-10-25 | **The repo is `corsu/ascolta`**; the old meetings folder keeps only `transcripts/` and `bakeoff/` (call data and public audio), with no git. | Corsu migration decisions 1 and 3. The transcript deny rules in `~/.claude/settings.json` and `~/.config/opencode/opencode.json` stay valid because that path did not change. | Active |
| D-012 | 2026-10-25 | **`PLAN.md` is split** into `docs/DESIGN.md`, `docs/DECISIONS.md` and `docs/STATUS.md`. | Corsu migration decision 5: one owner per fact. | Done |
| D-013 | 2026-10-26 | **Re-processing copies old outputs to `prev/`** instead of moving them (DESIGN said "move"). | A move leaves the call without its output when the re-run fails (a wrong pin, a VRAM timeout, invalid JSON); a copy keeps it in place and in `prev/`. Found by a letter-grade pass: the archiving was never built, so a re-run summarize overwrote a summary that can't be regenerated. | Active |

## Parked

| ID | Parked item | Revival trigger |
|---|---|---|
| P-001 | fscrypt on the data folder alone (protects a stolen disk, not agents) | The owner decides a stolen disk or a leaked backup belongs in the threat model |
| P-002 | A separate Unix user owning the data folder; the sandbox on for every Claude session | The owner decides to close the known gap in D-008 |
