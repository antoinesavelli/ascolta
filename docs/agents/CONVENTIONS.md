# Conventions

The shared code and test conventions (`AGENT_DOCTRINE.md` in the private system-library, *Code conventions*
and *Testing*), plus what ascolta adds.

- **One process per stage.** A stage is `ascolta <stage> <call-dir>`, run in sequence by `ascolta process`;
  a process exit frees all its GPU memory. Heavy libraries (faster-whisper, ctranslate2) are imported inside
  the function that needs them, so `ascolta --help` and the cheap stages stay light.
- **Model names appear only in `models.yaml`.** Code reads them through `ascolta.calls.load_models()`.
- **Every output is written atomically** (`write_atomic`: a temp file in the same folder, then a rename),
  and a stage is done only if the input hash it recorded still matches.
- **No transcript text in anything that is logged.** Error messages are `StageError` text built from IDs,
  counts and timings; a crash goes through `safe_trace`.
- **Tests never touch real call data.** Every test runs against a temporary `ASCOLTA_DATA` (the autouse
  `data` fixture); public clips come from `ASCOLTA_CLIPS` through `conftest.clip()`, which skips when the
  variable is unset and fails when a named clip is missing. Fake external dependencies (Ollama) in the
  failure-path tests; the pipeline tests use the real ones and carry the `gpu`/`ollama`/`pipewire` marks.
- **Types:** `mypy --strict` on `ascolta/`. `faster_whisper` ships no types, so `typings/faster_whisper/*.pyi`
  are hand-written stubs for the names ascolta uses (`mypy_path`); extend them when ascolta calls more of the
  library. No `ignore_missing_imports`, no type-ignore.
