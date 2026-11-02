# Ascolta: design

Status: settled by the owner 2026-10-23, revised 2026-10-24 (including the fixes from a blind re-grade,
C-); carried over from `PLAN.md` on 2026-10-25 when the plan was split into this file,
`docs/DECISIONS.md` and `docs/STATUS.md`. The owner's decisions are in `docs/DECISIONS.md`; what is built
and what is open is in `docs/STATUS.md`. "Tested" below means checked on this workstation on 2026-10-23/24.

## 1. Owner spec

Ascolta records, transcribes and summarizes calls on this workstation. All meetings: one
pipeline plus a small profile per person. Outputs are a transcript (with an English line under any
non-English segment), a summary and action items, nothing else: no interpreter notes, running per-person
notes, search or story archive.

## 2. Design

### Pipeline

- **One process per stage:** each stage is its own process (`ascolta <stage> <call-dir>`), run in sequence
  by `ascolta process`. A process exit frees all its GPU memory, whereas `unload_model()` alone leaves
  0.4 GB behind (tested). It also makes re-running a single stage work by design.
- **Per-call lock:** every stage holds `flock` on `<call>/.lock`, so the run after a recording and
  `--pending` can't process the same call at once.
- **Model names** appear only in `models.yaml` (see Models).

#### 1. Capture — `ascolta record <person>`

- **Channels:**
  - Left = my mic. Right = the default sink's monitor: the call plus any other system sound.
  - The channel split separates speakers exactly only in 2-person calls. Group calls get one `remote`
    speaker; there is no diarization model.
- **Mechanism** (routing tested end to end, with both monitor channels linked):
  1. Run `pw-record --target 0 --channels 2 --rate 48000 --format s16 --raw -`. Target `0` creates
     unlinked input ports.
  2. `pw-link` the mic's `capture_FL` to `input_FL`, and the sink's `monitor_FL` alone to `input_FR`.
     Call audio is mono. Linking both monitor channels to one port adds them together (up to +6 dB) and
     can clip.
  3. The recorder reads the PCM from stdout and encodes it with PyAV as 64 kbps Opus into `audio.opus`:
     26 MB/hour (tested), no ffmpeg needed.
  4. `run.json` records the source, sink and port names.
- **Plan B (decided 2026-10-24):** if the `pw-link` routing fails in phase 0, record two mono files
  instead, `mic.opus` and `remote.opus`, each from its own `pw-record`, with each start time in `run.json`.
- **Test results:** only the linked ports carried audio. A 440 Hz tone played into the headphones read
  −23 dBFS on the right and nothing on the left (mic floor −77 dBFS), so headphones give no bleed. The USB
  mic is mono: both ports carry your voice identically (−30 to −40 dBFS peak, within 0.2 dB), so
  `capture_FL` is right.
- **Phase 0 self-test (2026-10-24, `monitor_FL` alone):**
  - Your voice peaked −22 to −50 dBFS on the left, with the right at digital silence.
  - A public clip played through the headphone sink read −0.5 to −6 dBFS on the right, and the left rose
    only to about −56 dBFS. Near full scale means a loud call could clip.
  - Muting the mic gave exact zeros and the notification.
  - Switching to SPDIF and back relinked both times, within 8 s, with both notifications.
  - Ctrl+C (127 s) and `ascolta stop` (22 s, 68 s) each left a file that decodes to the end, and
    processing ran to exit 0.
  - **Design finding:** "call (right) is muted or unlinked" fired at the start of every recording, because
    an idle sink delivers exact zeros. The 5 s zero check can't tell "nothing playing" from "unlinked", so it
    will fire at the start of calls and in silent stretches.
- **Follow the default sink:** every 10 s, compare `pactl get-default-sink` with the linked sink. If it
  changed, relink the monitor and log the switch in `run.json`.
- **Fail loud with a desktop notification (`notify-send`):**
  - A channel delivers exact zeros for 5 s (muted or unlinked).
  - Or a channel's peak stays below −60 dBFS for 3 minutes.
  - At start, warn unless the default sink's `device.icon_name` is `audio-headphones` (true for this
    headphone sink, checked); speakers bleed the remote voice into the mic.
  - At start, warn if other apps are playing to the default sink (e.g. a browser tab): the right channel
    records everything the sink plays.
- **PID file:** `transcripts/.recording.pid` holds `pw-record`'s PID and start time.
  - `ascolta stop` sends SIGINT only if `/proc/<pid>/cmdline` is `pw-record` and the start time matches.
  - `ascolta record` refuses to start while a live PID file exists, and removes a stale one with a notice.
- **Stopping:**
  - Ctrl+C stops `pw-record`. The recorder ignores SIGINT, reads to the end of its input, closes the file,
    then starts processing.
  - A file cut off by a crash still decodes up to about its last second (tested).
- **At start:** print how many calls still have unfinished stages.
- **Any audio file:** `ascolta process <audio file>` accepts any audio path. A non-stereo file gets
  speaker `unknown`.

#### 2. Transcribe — TRANSCRIBER (faster-whisper)

- **Per channel:** transcribe each channel separately, then merge the segments by start time.
- **Chunks:** split speech with Silero VAD (`faster_whisper.vad`, ships with faster-whisper):
  - `min_silence_duration_ms=300`, `max_speech_duration_s=10` (so a chunk holds one language), and
    `min_speech_duration_ms=250`.
  - Merge chunks under 1 s into a neighbour before detecting their language.
  - Decode each chunk on its own.
  - Tested: without VAD, noise came back as "Thank you for watching…" (tagged `nn`); with VAD, the same
    noise produced no segments.
- **Language** (replaces `multilingual=True`, which picks one language per 30 s window out of 99,
  `transcribe.py:1192`):
  - `lang_mass` = the raw p(en) + p(fr) + p(es) from `detect_language`. Below 0.5, mark the chunk
    "⚠ other language", so Italian or Portuguese never comes out as confident Spanish.
  - `lang` = the top language among those three; `lang_prob` = its probability renormalized over the
    three. Transcribe with `lang` fixed. Never translate in place.
- **Decoding:** `hotwords` = the names in the person's profile. `condition_on_previous_text=False`.
- **Flags:** mark a segment ⚠ when any of these hold (phase 2 tunes the thresholds):
  - `no_speech_prob > 0.6`.
  - `avg_logprob < -1.0`.
  - `lang_prob < 0.7`.
  - The second language's renormalized probability is ≥ 0.3: "⚠ mixed".
- **`transcript.json`:** one record per segment with `start`, `end`, `speaker` (`me` | `remote` |
  `unknown`), `lang`, `lang_prob`, `lang_mass`, `text`, `en`, `flags`.

#### 3. Translate — TRANSLATOR

- **Text check before translating:**
  - Re-check segments labelled `en`. If at least 20% of the words are French or Spanish function words,
    relabel the segment, translate it, and mark it "⚠ language relabelled".
  - The word lists leave out words that are also English (e.g. "a", "on", "me", "pour").
- **What is translated:** every non-`en` segment, and every segment whose language probability is below
  0.7 (already marked ⚠), so a misdetected French sentence still gets English. The original is kept, with
  the English shown beneath it.
- **Ollama settings:**
  - An explicit system prompt that overrides any built-in one (mistral-small3.2 ships a "Le Chat"
    prompt).
  - Temperature 0, a fixed seed, and the `num_ctx` from `models.yaml`, all recorded in `run.json`.
  - **Context:** each request carries the 2 segments before and after the target, marked as context
    only; only the target is translated. A short fragment translated alone loses its meaning.
  - **Loading:** requests keep the model loaded for the whole stage, and the stage unloads it at the end
    (`keep_alive: 0`), so the GPU is free for the next stage and for other jobs. `keep_alive: 0` on every
    request would reload the 15 GB model for each segment.
- **Output check:** reject a translation that is empty, identical to the source, or outside 0.5–2× the
  source length. A rejected segment keeps its original text and gets "⚠ untranslated".

#### 4. Summarize — SUMMARIZER

- **Request:** Ollama `format` = JSON schema `{summary: [{text, ts, quote}], action_items: [{owner, text,
  ts, quote}]}`:
  - `owner` = `me` | `remote` | `unknown`.
  - `ts` has `pattern` `^[0-9]{1,3}:[0-9]{2}$`.
  - The summary is in English.
- **Settings:**
  - Set `think` explicitly (gpt-oss: low/medium/high).
  - `num_predict` 8192 (thinking tokens count against it); stop with an error if `done_reason` is
    `length`.
  - Temperature 0, a fixed seed, and `keep_alive: 0`, all recorded in `run.json`.
- **Tested:**
  - Without `owner`, gpt-oss wrote "Call the bank on Monday", with no owner.
  - Without `pattern`, it put "Monday" in `ts`. With both fields, it returned the right owners and
    `mm:ss` times.
- **Timestamp check:**
  - The grammar is enforced, so when no valid answer exists the model writes a well-formed wrong value
    (the re-grade got "202:00").
  - Code checks every `ts` and fails loud on a bad one: one that doesn't parse, or lies past the end of
    the call. That item gets "⚠ bad timestamp"; the rest of the summary stands.
  - Minutes may exceed 59 (`75:30`), so calls over an hour need no other format.
- **Not reproducible:** temperature 0 with a fixed seed is not reproducible (tested: one pair of runs
  differed, another matched). Keep every summary; never regenerate one silently.
- **Input:** the transcript as `[mm:ss] speaker: text`, plus the English line where there is one. The
  prompt names who is on the call and includes the profile's `summary_notes`.
- **Length guard:**
  - Before the request: estimate tokens as characters ÷ 3 (÷ 4 undercounts French and Spanish), and stop
    with an error above 80% of `num_ctx`.
  - After it: stop with an error if `prompt_eval_count` is ≥ 95% of `num_ctx`. Ollama truncates
    without an error.
  - No chunking until a real call needs it.

#### 5. Grounding check — code, not a model

- **Normalize:** lower-case (casefold), strip punctuation, collapse whitespace.
- **Pass rule:**
  - A quote must have at least 6 words; a shorter one gets "⚠ quote too short".
  - Join, in time order, the `text` of every segment within ±30 s of `ts`, and their `en` lines the same
    way.
  - A citation passes when some window of the quote's length, in either string, has a `difflib` ratio
    ≥ 0.9.
  - A window lets a quote from inside a long segment, or spanning two segments, match. Tested: the
    whole-segment ratio was 0.54 for a correct quote; the best window was 1.0.
- **What `summary.md` shows:**
  - A pass on `text`: "quote found". A pass only on `en`: "found in translation", since that rests on
    machine translation. Never "verified": the check proves the quote exists, not that it supports the
    item, so every item shows its quote and the reader judges support.
  - A failed citation: "⚠ quote not found".
  - A bullet or action item with no citation: "⚠ uncited".
  - A citation that lands on a ⚠ segment: the segment's ⚠.
- **Nothing is dropped:** failures stay visible.

### Files, resuming and failures

`transcripts/<date>_<time>_<person>/` holds `audio.opus`, `segments.json` (the transcriber's output),
`transcript.json` (segments plus `en`), `transcript.md`, `summary.json` (the summarizer's raw items, kept
because it can't be regenerated identically), `summary.md`, `run.json` and `.lock`. Each stage writes its
own files, so a stage's input hash never changes under it.

**Data folder:** `ASCOLTA_DATA` is required and names the folder that holds every call and profile: there is
no default path in code, and the pipeline stops with an error naming the variable when it is unset
(decision D-010). On this workstation it is a folder outside the repo, set by the
`~/.local/bin/ascolta` wrapper. Tests and the bake-off always use a temporary folder: the repo's sandbox
blocks the real one, and test data must never mix with real calls. Public test clips live outside the repo,
in the folder `ASCOLTA_CLIPS` names (a folder outside the repo here).

**Profiles:** `transcripts/people/<name>.yaml` holds:
- `name`.
- `hotwords`: names Whisper should recognize.
- `summary_notes`: a few lines of free text about the person, added verbatim to the summarizer prompt.

**`run.json`, per stage:** model, full Ollama digest or Hugging Face revision, parameters, the sha256 of
the inputs (including the profile), status, start/end times, error.

#### Resuming and failures

- **Writes:** every output, and `run.json`, is written to a temp file in the same folder and then renamed
  into place (a rename is atomic only within one filesystem).
- **Done:** a stage counts as done only if the input sha256 it recorded matches its current inputs.
  Otherwise it is stale, and so is every stage after it. `ascolta process` re-runs stale or missing
  stages; `ascolta process --pending` does that for every call.
- **GPU memory:**
  - Before each stage, check that free VRAM covers the stage's `vram_gb` from `models.yaml`. For Ollama
    stages, count memory Ollama already holds (`size_vram` from `/api/ps`) as free, since Ollama evicts
    its own model.
  - If short, notify and wait up to 30 minutes (local agents share this GPU). Past that, the stage fails
    and stays pending, and `ascolta process --pending` picks it up later.
  - Ollama here keeps one model loaded (`OLLAMA_MAX_LOADED_MODELS=1`) and swapped one model for the other
    on its own, entirely on the GPU (tested).
- **Notifications:** sent on success and on failure. They carry counts only (e.g. "alex: 7 action items,
  1 ⚠"), never call content.
- **Re-processing:** before a stage runs, copy each output it already has to
  `<call>/prev/<stage>.<UTC timestamp>.<ext>` (`calls.archive_outputs`). Git does not keep these files, so
  overwriting would lose them. A copy, not a move (D-013): if the re-run fails, the current output stays in place.

### Privacy and agent access

**Rule:** paid-API agents (Claude Code, opencode with OpenRouter, …) never read call data. Only the local
models inside the pipeline do.

A project Read-deny rule alone does not enforce this. Per the Claude Code docs it does not stop
`grep -r` or a Python script, and it only applies to sessions whose working directory is this repo
(including after a `/cd`). Ollama's log holds no prompt text (tested: a test prompt appeared 0 times).
Layers, the hard one first:

1. **Sandbox in this repo:** `.claude/settings.json` sets
   `sandbox: {enabled: true, failIfUnavailable: true, allowUnsandboxedCommands: false}` and denies the whole
   `mcp__terminal` server (since 2026-10-25; `read_terminal` alone left `run_in_terminal` and
   `stop_terminal_tab` open). The untracked `.claude/settings.local.json` denies `Read` and `Edit` on the
   call-data folder's `transcripts/**`, so that path stays out of the public repo (since 2026-11-02).
   - The deny paths are enforced at the OS level: bubblewrap mounts an empty tmpfs over `transcripts/`, so
     `grep -r`, `python` and the pipeline see nothing (proved 2026-10-24, layer 6). The same sandbox also
     blocks `/dev/nvidia*`, `localhost:11434` and the PipeWire socket.
   - Per the Claude Code docs, a command would run unsandboxed if the sandbox failed to start, or if a
     blocked command were retried unsandboxed. The two settings close both.
   - File tools, MCP tools and hooks run outside the sandbox. The deny rules cover the file tools and the
     terminal-reading tool.
2. **The same deny rules in `~/.claude/settings.json`, plus a `read` deny for the same path in
   `~/.config/opencode/opencode.json`.** You apply both (persistent config), so Claude sessions started
   anywhere are blocked too.
   - The Claude rules cover only the file tools and `cat`/`head`/`sed`, not scripts.
   - opencode 1.18.31 matches `read` permissions by path (its built-in default is
     `read: {"*": "allow", "*.env": "ask", …}`). The `read` deny for this path does not work (tested
     2026-10-24, in either rule order). A top-level `external_directory: {"…/transcripts/*": "deny"}` blocks
     the read tool for the default agent, in subfolders too (applied and verified 2026-10-25). opencode's
     bash tool is not covered.
3. **No transcript text in logs.** The pipeline's logs, stdout, stderr and notifications carry IDs,
   counts, timings and ⚠ counts only, on failure paths too. Tests 4 and 8 enforce it.
4. **Private test material:** your self-recorded clips and their reference transcripts (your voice, plus
   the profile names) live in `transcripts/bakeoff-private/`, not in `bakeoff/data/`, which holds public
   audio only. Agents can't read them, so you run the bake-off's private arm yourself; agents see only its
   scores.
5. **`AGENTS.md`:**
   - States the rule.
   - Agents debug only with public or synthetic audio in `bakeoff/data/`.
   - Never run opencode in or above the folder that holds the call data: its path deny covers only its read tool, and it is
     configured with OpenRouter.
   - Never open call files in the app's terminal panel.
6. **Proof before the first real call:** with a dummy file in `transcripts/` (no real content):
   - In a Claude session started in the repo, these must all fail on it: the Read tool, `cat`, `grep -r`,
     `python -c "open(...)"`, a retry outside the sandbox, and `mcp__terminal__read_terminal`.
   - In a session started elsewhere, or one that `/cd`s out of the repo: the Read tool and `cat` must
     fail.
   - opencode's read tool must fail on it.

**Known gap (accepted 2026-10-24):** two routes have no hard block:
- Scripts run by Claude sessions started outside this repo, or that `/cd` out of it.
- opencode's bash tool.

The sandbox's own escape routes in layer 1 were also on this list; the two sandbox settings now close
them. Turning the sandbox on for every session, or a separate Unix user owning `transcripts/`, would close
more. You chose layered rules instead.


### Git safety

The repo is public (decision D-009), so call data and audio stay out of it by refusal, not by being local.

- **`.gitignore`:** `transcripts/`, the audio extensions (opus, ogg, wav, flac, mp3, m4a, webm) and
  `bakeoff/data/`.
- **Hooks** (`core.hooksPath` is `.githooks`; set it once per clone with `git config core.hooksPath .githooks`):
  - `.githooks/pre-commit` refuses credentials and every staged path matching a glob in
    `.githooks/refuse`: `transcripts/*` and the audio extensions, matched case-insensitively.
  - `.githooks/pre-push` runs `gitleaks git` over the whole history and blocks the push on a finding or a
    missing gitleaks.
- **Agents:** creating the remote and every push are ask-first, the owner's call (`AGENTS.md`). The
  repo's `.claude/settings.json` keeps the `mcp__terminal` deny, and the untracked
  `.claude/settings.local.json` the transcript Read/Edit denies.
- **Test 4 checks:**
  - `git ls-files` holds none of the ignored paths, and `git check-ignore` matches a sample call path.
  - `git config core.hooksPath` is `.githooks`.
  - The pre-commit hook rejects a staged dummy `.opus` and a staged `transcripts/` path in a temporary repo.

### Models

- **`models.yaml` owns the model names, pins and needs.** Load with `local_files_only=True`. Initial
  content, with VRAM tested at these contexts:

  ```yaml
  transcriber: {name: Systran/faster-whisper-large-v3, revision: edaa852ec7e145841d8ffdb056a99866b5f0a478, vram_gb: 4.6}
  translator: {name: mistral-small3.2:24b, digest: 5a408ab55df5c1b5cf46533c368813b30bf9e4d8fc39263bf2a3338cfa3b895b, num_ctx: 4096, vram_gb: 17}
  summarizer: {name: gpt-oss:20b-64k, digest: 36f80c24f1036e0a75072dad7e899938e97f8a143c11b9282047bb61aa2e4705, vram_gb: 12}
  ```

  - The translator's 17 GB was measured at its default 32k context; re-measuring it at 4096 is open (`docs/STATUS.md`).
  - `run.json` copies the pins.
- **Pins are checked when the pipeline runs:**
  - The transcriber loads with `WhisperModel(..., revision=<pin>)`.
  - Each Ollama stage compares the tag's current digest (from `/api/tags`) with the pin and stops on a
    mismatch, because a re-pull can change the weights behind a tag.
- **Drift check:** `system-library/machines/workstation/model-routing.yaml` gets three `tool: dotfile`
  entries.
  - Each has `file:` pointing at `models.yaml`, a `field:` regex capturing one stage's `name` (e.g.
    `(?m)^summarizer: \{name: ([^,]+),`), and that name as `slug`.
  - That lets `scripts/check_model_config_sync.py` catch drift; a comment-only pointer would be invisible
    to it.
- **Changes need you:** the bake-off writes `models.proposed.yaml` with links to its evidence; you apply it.

### Bake-off (phase 2)

- **Environment:** candidates live in their own uv venv or dependency group, so the pipeline's venv stays
  lean. Claude does not judge.
- **Statistics:** use a paired bootstrap of the score difference on the same items (1,000 resamples, drawn
  by meeting or utterance). A candidate wins only if the 95% interval of the difference excludes 0;
  otherwise the smaller or faster model wins.
- **Jobs:**
  - One output file per model and item; existing ones are skipped, so a killed run resumes.
  - Before a full run, time one meeting and state the estimated GPU-hours.
  - Run when the GPU is free.

**Test sets and sizes** (licenses checked 2026-10-23):
- **English, by mic quality:** AMI's standard ASR eval meetings (CC BY 4.0), scored three ways on the same
  speech and references:
  - Headset audio.
  - Distant-mic audio.
  - Phone-band: the headset audio resampled to 8 kHz and encoded as 16 kbps Opus.
- **English 2-person conversation:** all 57 PriMock57 consultations (CC BY 4.0).
- **French and Spanish:** the full FLEURS test splits for `fr_fr` and `es_419` (CC BY 4.0), which also
  have parallel English references.
- **Code-switching and names:** 20 clips of about 1 minute that you record yourself, mixing en/fr/es and
  using the profile hotwords. You write their reference transcripts; both stay in
  `transcripts/bakeoff-private/` (Privacy, layer 4). No public French–English code-switching corpus
  exists.
- **Summaries:** the 133 AMI meetings that have `actions` (counted from a mirror; recount after download):
  - 20 are for calibrating the match threshold.
  - The other 113 are for scoring, with 2 runs per meeting because outputs aren't reproducible.
- **Excluded:**
  - Earnings-21/22: audio license unstated.
  - TalkBank / Bangor Miami: CC BY-NC-SA, and its rules bar uploading to Anthropic without a no-storage
    option.
  - CS-FLEURS (non-commercial), SPGISpeech (academic use only), and Switchboard, Fisher and CallHome (paid
    LDC licenses).

**Arms:**
- **Transcriber:**
  - **Candidates:** Whisper large-v3, turbo and medium, against Parakeet-tdt-0.6b-v3 (CC-BY-4.0; detects
    language itself) and Canary-1b-v2 (CC-BY-4.0; needs the language given, so it uses step 2's
    detection). Run Parakeet and Canary through onnx-asr (MIT), not NeMo 3.0 (Python ≥ 3.12, torch ≥ 2.7,
    ~150–200 packages).
  - **Scores:**
    - WER, using Whisper's English normalizer, per mic quality and on PriMock57.
    - WER per language on FLEURS.
    - Name recall on your clips.
- **Translator:**
  - **Candidates:** Ollama LLMs and MADLAD-400 (Apache-2.0). NLLB-200 is dropped: its non-commercial
    license (CC-BY-NC) doesn't fit work meetings, and MADLAD covers the same role.
  - **Score:** chrF (sacrebleu) on FLEURS fr→en and es→en.
- **Summarizer:**
  - **Candidates:** Ollama models on disk.
  - **Input:** the production task, not a hand transcript. Each meeting's headset-mix audio runs through
    the pipeline's transcriber, then the production prompt and schema (`owner` = `unknown`, since AMI has
    4 speakers).
  - **Score:** action-item precision and recall (F1), plus the grounding pass rate, against AMI's human
    `actions` summaries (about 306 sentences).
  - **Matching:** an item matches a reference when their `nomic-embed-text` cosine similarity reaches a
    threshold; matching is one-to-one.
  - **Setting the threshold:**
    1. On the 20 calibration meetings, you label about 100 item–reference pairs as match or not.
    2. The threshold that agrees best with your labels is frozen before scoring.
  - **Blind pick:** for 10 AMI meetings, you see the finalists' summaries side by side, in random order and
    without model names, and pick the best one each time. Most picks wins; a tie goes to the smaller model.

**Before switching models:** process 3 of your own calls with the current and the proposed models. You
pick blind (local only, no agent involved). Switch only if the new models win at least 2 of 3. These are
the only test calls that resemble yours.

**Re-processing:** run one older call first, check it, then do the rest. Old outputs go to `prev/`.

### Tests (public or synthetic audio only)

Public clips come from the folder `ASCOLTA_CLIPS` names. Unset, the tests that need a clip skip with a reason
naming the variable; set, a clip that is missing fails.

1. **Grounding:**
   - An exact quote passes, including one from inside a long segment and one spanning two segments.
   - A paraphrase fails; the right quote at the wrong time fails.
   - An uncited bullet is flagged, and a quote under 6 words is flagged.
   - A match only on `en` shows "found in translation".
2. **Synthetic stereo** (speech left, noise right): only `me` segments come out, no `remote` lines.
3. **End to end** on one public 2-person clip (PriMock57): every stage runs, `transcript.json` matches the
   schema, `run.json` is complete.
4. **Privacy and git:** the Git safety checks above. Also, no test wrote under `transcripts/`, and test 3's
   logs, stdout and stderr contain no transcript text.
5. **Language:**
   - English followed by German (faster-whisper's MIT `multilingual.mp3`) comes out `en`, then
     "⚠ other language". French audio isn't covered yet: no public French clip is on disk, so your
     self-recorded clips fill this gap.
   - An English sentence stays `en`.
   - An `en`-labelled French sentence gets relabelled and translated.
   - An Italian FLEURS clip gets "⚠ other language".
6. **Routing** (needs PipeWire): a `pw-loopback` virtual sink stands in for the call, playing a tone. The
   right channel reads it; the left doesn't.
7. **Staleness and pins**, on a fake call folder:
   - Editing `transcript.json` makes the summary stale.
   - A wrong digest in `models.yaml` stops the Ollama stage.
8. **Failure paths:** a forced bad `ts` and a rejected translation. The run marks both ⚠, and its logs and
   stderr contain no transcript text.

## 3. Module split

One module per stage, one process per stage (`ascolta <stage> <call-dir>`); every model name lives in
`models.yaml`.

| Module | Owns |
|---|---|
| `ascolta/cli.py` | The command line: `record`, `stop`, `process [--pending]`, and the internal `stage` |
| `ascolta/calls.py` | Call folders, `run.json`, stage staleness, the per-call lock, VRAM waits, notifications, the `ASCOLTA_DATA` folder |
| `ascolta/record.py` | Capture: mic left, default sink's monitor right, 64 kbps Opus, the PID file |
| `ascolta/transcribe.py` | TRANSCRIBER: per-channel VAD chunks, en/fr/es language per chunk, faster-whisper decoding |
| `ascolta/translate.py` | TRANSLATOR: an English line under each non-English segment |
| `ascolta/summarize.py` | SUMMARIZER: summary and action items with a timestamp and an exact quote each |
| `ascolta/ground.py` | Grounding check in code, and `summary.md` |
| `ascolta/ollama.py` | Minimal client for the local Ollama server: chat, pin check, loaded VRAM, unload |
| `models.yaml` | Model names, pins, VRAM needs and `num_ctx`: the only place a model name appears |
