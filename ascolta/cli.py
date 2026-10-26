"""Command line: `ascolta record <person>`, `ascolta stop`, `ascolta process [...]`, and the internal `stage`.

Depends on: ascolta.calls (orchestration), ascolta.record (capture).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from ascolta.calls import (
    AUDIO_SUFFIXES,
    STAGES,
    StageError,
    all_calls,
    is_done,
    new_call,
    process,
    run_stage,
    safe_trace,
    update_run,
)


def import_audio(path: Path, person: str) -> Path:
    """Copy any audio file into a new call folder."""
    if path.suffix.lower() not in AUDIO_SUFFIXES:
        raise StageError(f"not an audio file: {path.suffix or 'no extension'}")
    call = new_call(person)
    shutil.copy2(path, call / f"audio{path.suffix.lower()}")
    update_run(call, source=str(path.resolve()))
    return call


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ascolta")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("record", help="record a call until Ctrl+C or `ascolta stop`").add_argument(
        "person"
    )
    sub.add_parser("stop", help="stop the running recording")
    proc = sub.add_parser("process", help="run every stale or missing stage")
    proc.add_argument("target", nargs="?", type=Path, help="a call folder or any audio file")
    proc.add_argument("--pending", action="store_true", help="every call with unfinished stages")
    proc.add_argument(
        "--person", default="unknown", help="who the call was with (for an audio file)"
    )
    stage = sub.add_parser("stage", help="run one stage on a call folder (used by process)")
    stage.add_argument("name", choices=STAGES)
    stage.add_argument("call", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            from ascolta.record import record

            ok = process(record(args.person))
        elif args.command == "stop":
            from ascolta.record import stop

            stop()
            ok = True
        elif args.command == "stage":
            run_stage(args.name, args.call.resolve())
            ok = True
        elif args.pending:
            pending = [c for c in all_calls() if not all(is_done(c, s) for s in STAGES)]
            results = [process(c) for c in pending]  # every call runs; none is skipped
            ok = all(results)
        elif args.target is not None:
            target = args.target.resolve()
            ok = process(target if target.is_dir() else import_audio(target, args.person))
        else:
            parser.error("give a call folder or audio file, or --pending")
    except StageError as err:
        print(f"ascolta: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"ascolta: crashed: {safe_trace(err)}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if ok else 1)
