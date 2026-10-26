"""TRANSCRIBER stage: per-channel speech chunks, an en/fr/es language per chunk, faster-whisper decoding.

Depends on: faster-whisper (Silero VAD, detect_language), PyAV, models.yaml `transcriber`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import av
import numpy as np

from ascolta.calls import audio_file, load_models, load_profile, person_of, write_json

SR = 16000
LANGS = ("en", "fr", "es")
VAD = {"min_silence_duration_ms": 300, "max_speech_duration_s": 10, "min_speech_duration_ms": 250}
OTHER_LANGUAGE, MIXED, LOW_LANGUAGE = 0.5, 0.3, 0.7
NO_SPEECH, LOW_LOGPROB = 0.6, -1.0


def speakers(path: Path) -> list[tuple[str, np.ndarray]]:
    """Stereo calls: left = me, right = remote. Anything else is one `unknown` track."""
    from faster_whisper import decode_audio

    with av.open(str(path)) as container:
        channels = container.streams.audio[0].channels
    if channels == 2:
        left, right = decode_audio(str(path), sampling_rate=SR, split_stereo=True)
        return [("me", left), ("remote", right)]
    return [("unknown", decode_audio(str(path), sampling_rate=SR))]


def chunks(audio: np.ndarray) -> list[tuple[int, int]]:
    """VAD speech spans in samples; a span under 1 s is merged into its neighbour."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    merged: list[tuple[int, int]] = []
    for span in get_speech_timestamps(audio, VadOptions(**VAD), sampling_rate=SR):
        start, end = span["start"], span["end"]
        if merged and (end - start < SR or merged[-1][1] - merged[-1][0] < SR):
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def choose_language(model: Any, audio: np.ndarray) -> tuple[str, float, float, float]:
    """(language, its probability renormalized over en/fr/es, the runner-up's, raw en+fr+es mass)."""
    _, _, probs = model.detect_language(audio=audio)
    raw = {code: p for code, p in probs if code in LANGS}
    mass = sum(raw.values())
    norm = {c: raw.get(c, 0.0) / mass if mass else 1 / len(LANGS) for c in LANGS}
    first, second = sorted(LANGS, key=norm.__getitem__, reverse=True)[:2]
    return first, norm[first], norm[second], mass


def chunk_flags(lang_prob: float, runner_up: float, mass: float) -> list[str]:
    flags = []
    if mass < OTHER_LANGUAGE:
        flags.append("other language")
    if runner_up >= MIXED:
        flags.append("mixed")
    if lang_prob < LOW_LANGUAGE:
        flags.append("low language confidence")
    return flags


def run(call: Path) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    cfg = load_models()["transcriber"]
    profile, _ = load_profile(person_of(call))
    model = WhisperModel(
        cfg["name"],
        device="cuda",
        compute_type="float16",
        local_files_only=True,
        revision=cfg["revision"],
    )
    hotwords = " ".join(profile["hotwords"]) or None
    segments, duration = [], 0.0
    for speaker, audio in speakers(audio_file(call)):
        duration = max(duration, len(audio) / SR)
        for start, end in chunks(audio):
            piece, offset = audio[start:end], start / SR
            lang, lang_prob, runner_up, mass = choose_language(model, piece)
            flags = chunk_flags(lang_prob, runner_up, mass)
            decoded, _ = model.transcribe(
                piece,
                language=lang,
                hotwords=hotwords,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            for seg in decoded:
                if not seg.text.strip():
                    continue
                seg_flags = list(flags)
                if seg.no_speech_prob > NO_SPEECH:
                    seg_flags.append("maybe not speech")
                if seg.avg_logprob < LOW_LOGPROB:
                    seg_flags.append("low confidence")
                segments.append(
                    {
                        "start": round(offset + seg.start, 2),
                        "end": round(offset + seg.end, 2),
                        "speaker": speaker,
                        "lang": lang,
                        "lang_prob": round(lang_prob, 3),
                        "lang_mass": round(mass, 3),
                        "text": seg.text.strip(),
                        "en": None,
                        "flags": seg_flags,
                    }
                )
    segments.sort(key=lambda s: (s["start"], s["speaker"]))
    write_json(call / "segments.json", {"duration_s": round(duration, 2), "segments": segments})
    return {
        "model": cfg["name"],
        "pin": cfg["revision"],
        "params": {**VAD, "langs": LANGS, "hotwords": len(profile["hotwords"])},
        "counts": {"segments": len(segments), "⚠": sum(bool(s["flags"]) for s in segments)},
    }
