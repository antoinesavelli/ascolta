"""SUMMARIZER stage: an English summary and action items, each citing a timestamp and an exact quote.

Depends on: ascolta.ollama, models.yaml `summarizer`. Output is kept as summary.json and never
regenerated silently: the model is not reproducible even at temperature 0 with a seed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ascolta import ollama
from ascolta.calls import StageError, load_models, load_profile, person_of, write_json
from ascolta.translate import mmss

SEED, THINK, NUM_PREDICT = 7, "medium", 8192
CHARS_PER_TOKEN, MAX_PROMPT_SHARE, TRUNCATED_SHARE = 3, 0.8, 0.95
CITED = {
    "text": {"type": "string"},
    "ts": {"type": "string", "pattern": "^[0-9]{1,3}:[0-9]{2}$"},
    "quote": {"type": "string"},
}
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "array",
            "items": {"type": "object", "properties": CITED, "required": ["text", "ts", "quote"]},
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "enum": ["me", "remote", "unknown"]},
                    **CITED,
                },
                "required": ["owner", "text", "ts", "quote"],
            },
        },
    },
    "required": ["summary", "action_items"],
}
SYSTEM = (
    "You summarize a call transcript in English. Each line is `[mm:ss] speaker: text`, sometimes followed "
    "by an English translation in parentheses. Speaker `me` recorded the call, `remote` is everyone else on "
    "it, `unknown` means the speaker is not known.\n"
    "Return JSON with:\n"
    "- summary: the key points. Each has text (one sentence), ts (the mm:ss of the line you quote) and "
    "quote (at least 6 consecutive words copied exactly from that line).\n"
    "- action_items: what someone agreed or was asked to do. Each has owner (me, remote or unknown), text, "
    "ts and quote, with the same rules.\n"
    "Quote only words that appear in the transcript. If there are no action items, return an empty list."
)


def transcript_lines(segments: list[dict[str, Any]]) -> str:
    lines = []
    for s in segments:
        line = f"[{mmss(s['start'])}] {s['speaker']}: {s['text']}"
        lines.append(f"{line}  (en: {s['en']})" if s.get("en") else line)
    return "\n".join(lines)


def validate(content: str) -> dict[str, list[dict[str, Any]]]:
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise StageError("the summarizer returned invalid JSON") from None
    for key, fields in (
        ("summary", ("text", "ts", "quote")),
        ("action_items", ("owner", "text", "ts", "quote")),
    ):
        items = result.get(key)
        if not isinstance(items, list) or not all(
            isinstance(i, dict) and all(f in i for f in fields) for i in items
        ):
            raise StageError(f"the summarizer's {key} is missing required fields")
    return {"summary": result["summary"], "action_items": result["action_items"]}


def run(call: Path) -> dict[str, Any]:
    segments = json.loads((call / "transcript.json").read_text())["segments"]
    profile, _ = load_profile(person_of(call))
    cfg = load_models()["summarizer"]
    num_ctx = cfg["num_ctx"]
    notes = (
        f"\nNotes about {profile['name']}: {profile['summary_notes']}"
        if profile["summary_notes"]
        else ""
    )
    user = f"On this call, remote is {profile['name']}.{notes}\n\nTranscript:\n{transcript_lines(segments)}"
    estimate = (len(SYSTEM) + len(user)) // CHARS_PER_TOKEN
    if estimate > MAX_PROMPT_SHARE * num_ctx:
        raise StageError(f"transcript too long: about {estimate} tokens for num_ctx {num_ctx}")
    ollama.check_pin(cfg["name"], cfg["digest"])
    options = {"temperature": 0, "seed": SEED, "num_ctx": num_ctx, "num_predict": NUM_PREDICT}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    reply = ollama.chat(cfg["name"], messages, options, keep_alive=0, fmt=SCHEMA, think=THINK)
    if reply.get("done_reason") == "length":
        raise StageError(f"the summary was cut off at num_predict {NUM_PREDICT}")
    if reply.get("prompt_eval_count", 0) >= TRUNCATED_SHARE * num_ctx:
        raise StageError(
            f"the prompt filled {reply['prompt_eval_count']} of {num_ctx} tokens and may be truncated"
        )
    result = validate(reply["message"]["content"])
    write_json(call / "summary.json", result)
    return {
        "model": cfg["name"],
        "pin": cfg["digest"],
        "params": {**options, "think": THINK},
        "counts": {
            "points": len(result["summary"]),
            "action items": len(result["action_items"]),
            "prompt tokens": reply.get("prompt_eval_count", 0),
        },
    }
