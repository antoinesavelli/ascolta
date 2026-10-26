"""TRANSLATOR stage: an English line under each non-English segment; the original is kept.

Depends on: ascolta.ollama, models.yaml `translator`.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ascolta import ollama
from ascolta.calls import load_models, person_of, write_atomic, write_json

SEED, CONTEXT, LOW_LANGUAGE, RELABEL_SHARE = 7, 2, 0.7, 0.2
# Function words only, leaving out any that are also English words ("a", "on", "me", "pour", "son", "no", "al").
FUNCTION_WORDS = {
    "fr": frozenset(
        "je tu il elle nous vous ils elles est sont suis pas les des une du aux avec dans mais oui très "
        "c'est j'ai qu'il qui quoi pourquoi parce alors aussi bien merci donc ça ce cette mes ton tes "
        "notre votre leur le la et ou sur".split()
    ),
    "es": frozenset(
        "el los las una unos unas del pero porque también muy está están estoy es soy qué sí yo él ella "
        "nosotros ustedes ellos para por como cómo cuando donde dónde tengo tiene bueno gracias entonces "
        "pues eso esto esta este su sus lo hola".split()
    ),
}
SYSTEM = (
    "You translate one segment of a phone-call transcript into English. Lines marked CONTEXT are only "
    "there for meaning: do not translate them. Reply with the English translation of the TARGET line "
    "and nothing else."
)


def relabel(text: str) -> str | None:
    """The language an `en`-labelled segment is really in, when its function words say so."""
    words = re.findall(r"[\w']+", text.casefold())
    if len(words) < 3:
        return None
    hits = {lang: sum(w in vocab for w in words) for lang, vocab in FUNCTION_WORDS.items()}
    lang = max(hits, key=hits.__getitem__)
    return lang if hits[lang] / len(words) >= RELABEL_SHARE else None


def same_text(a: str, b: str) -> bool:
    return SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio() >= 0.8


def acceptable(source: str, english: str) -> bool:
    ratio = len(english) / max(len(source.strip()), 1)
    return bool(english) and not same_text(source, english) and 0.5 <= ratio <= 2.0


def prompt(segments: list[dict[str, Any]], i: int) -> str:
    lines = []
    for j in range(max(0, i - CONTEXT), min(len(segments), i + CONTEXT + 1)):
        tag = "TARGET" if j == i else "CONTEXT"
        lines.append(f"{tag} ({segments[j]['lang']}): {segments[j]['text']}")
    return "\n".join(lines)


def mmss(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def render(call: Path, segments: list[dict[str, Any]]) -> str:
    out = [
        f"# {call.name}",
        "",
        f"Left channel = me; right channel = remote ({person_of(call)}).",
        "",
    ]
    for s in segments:
        marks = "".join(f" ⚠ {f}" for f in s["flags"])
        out.append(f"[{mmss(s['start'])}] {s['speaker']} ({s['lang']}): {s['text']}{marks}")
        if s.get("en"):
            out.append(f"        en: {s['en']}")
    return "\n".join(out) + "\n"


def translate_all(
    segments: list[dict[str, Any]], todo: list[int], name: str, options: dict[str, Any]
) -> None:
    """Set `en` on each todo segment whose translation is acceptable; flag a rejected non-English one."""
    for i in todo:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt(segments, i)},
        ]
        english = ollama.chat(name, messages, options, keep_alive="5m")["message"][
            "content"
        ].strip()
        s = segments[i]
        if acceptable(s["text"], english):
            s["en"] = english
        elif s["lang"] != "en":
            s["flags"].append("untranslated")


def run(call: Path) -> dict[str, Any]:
    data = json.loads((call / "segments.json").read_text())
    segments = data["segments"]
    for s in segments:
        lang = relabel(s["text"]) if s["lang"] == "en" else None
        if lang:
            s["lang"] = lang
            s["flags"].append("language relabelled")
    cfg = load_models()["translator"]
    todo = [i for i, s in enumerate(segments) if s["lang"] != "en" or s["lang_prob"] < LOW_LANGUAGE]
    options = {"temperature": 0, "seed": SEED, "num_ctx": cfg["num_ctx"]}
    if todo:
        ollama.check_pin(cfg["name"], cfg["digest"])
    try:
        translate_all(segments, todo, cfg["name"], options)
    finally:
        if todo:
            ollama.unload(cfg["name"])
    write_json(call / "transcript.json", data)
    write_atomic(call / "transcript.md", render(call, segments))
    return {
        "model": cfg["name"],
        "pin": cfg["digest"],
        "params": {**options, "context_segments": CONTEXT},
        "counts": {
            "translated": sum(bool(s["en"]) for s in segments),
            "untranslated": sum("untranslated" in s["flags"] for s in segments),
        },
    }
