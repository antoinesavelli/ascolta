"""Grounding check, in code: every cited quote must exist near its timestamp; failures stay visible.

Depends on: summary.json and transcript.json in the call folder.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ascolta.calls import write_atomic
from ascolta.translate import mmss

MIN_WORDS, WINDOW_S, MIN_RATIO = 6, 30, 0.9


def normalize(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text.casefold()).split()


def parse_ts(ts: str) -> int | None:
    match = re.fullmatch(r"(\d{1,3}):([0-5]\d)", ts.strip())
    return int(match[1]) * 60 + int(match[2]) if match else None


def best_window(
    quote: list[str], segments: list[dict[str, Any]], field: str
) -> tuple[float, list[dict[str, Any]]]:
    """Best difflib ratio of the quote against any run of as many words, joined across segments in time order."""
    words, owners = [], []
    for s in segments:
        for word in normalize(s.get(field) or ""):
            words.append(word)
            owners.append(s)
    target, best, hit = " ".join(quote), 0.0, []
    for i in range(max(len(words) - len(quote), 0) + 1):
        window = words[i : i + len(quote)]
        ratio = SequenceMatcher(None, target, " ".join(window)).ratio() if window else 0.0
        if ratio > best:
            best, hit = ratio, owners[i : i + len(quote)]
    return best, hit


def locate(words: list[str], near: list[dict[str, Any]]) -> str:
    """`quote found` in the original, else `found in translation`, plus the hit segments' flags."""
    for field, label in (("text", "quote found"), ("en", "found in translation")):
        ratio, hit = best_window(words, near, field)
        if ratio >= MIN_RATIO:
            flags = sorted({f for s in hit for f in s["flags"]})
            return label + "".join(f" ⚠ {f}" for f in flags)
    return "⚠ quote not found"


def check(item: dict[str, Any], segments: list[dict[str, Any]], duration: float) -> str:
    """The label shown under an item: `quote found`, `found in translation`, or a ⚠ reason."""
    quote, ts = str(item.get("quote") or ""), str(item.get("ts") or "")
    if not quote.strip() or not ts.strip():
        return "⚠ uncited"
    at = parse_ts(ts)
    if at is None or at > duration + 1:
        return "⚠ bad timestamp"
    words = normalize(quote)
    if len(words) < MIN_WORDS:
        return "⚠ quote too short"
    near = [s for s in segments if s["start"] <= at + WINDOW_S and s["end"] >= at - WINDOW_S]
    return locate(words, near)


def render(
    call: Path, result: dict[str, list[dict[str, Any]]], labels: dict[str, list[str]]
) -> str:
    out = [f"# Summary — {call.name}", "", "## Summary"]
    for item, label in zip(result["summary"], labels["summary"], strict=True):
        out += [f"- {item['text']}", f'  > "{item["quote"]}" [{item["ts"]}] — {label}']
    out += ["", "## Action items"]
    for item, label in zip(result["action_items"], labels["action_items"], strict=True):
        out += [
            f"- ({item['owner']}) {item['text']}",
            f'  > "{item["quote"]}" [{item["ts"]}] — {label}',
        ]
    if not result["action_items"]:
        out.append("- none")
    return "\n".join(out) + "\n"


def run(call: Path) -> dict[str, Any]:
    transcript = json.loads((call / "transcript.json").read_text())
    result = json.loads((call / "summary.json").read_text())
    segments, duration = transcript["segments"], transcript["duration_s"]
    labels = {
        key: [check(item, segments, duration) for item in result[key]]
        for key in ("summary", "action_items")
    }
    write_atomic(call / "summary.md", render(call, result, labels))
    all_labels = labels["summary"] + labels["action_items"]
    return {
        "params": {
            "min_words": MIN_WORDS,
            "window_s": WINDOW_S,
            "min_ratio": MIN_RATIO,
            "length_s": mmss(duration),
        },
        "counts": {
            "action items": len(result["action_items"]),
            "⚠": sum("⚠" in label for label in all_labels),
        },
    }
