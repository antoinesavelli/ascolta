"""Hand-written stubs for the names ascolta uses; faster-whisper ships no types.

Signatures follow faster-whisper 1.2.1 (`audio.py`, `transcribe.py`).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, overload

import numpy as np

@overload
def decode_audio(
    input_file: str, sampling_rate: int = 16000, split_stereo: Literal[False] = False
) -> np.ndarray: ...
@overload
def decode_audio(
    input_file: str, sampling_rate: int = 16000, *, split_stereo: Literal[True]
) -> tuple[np.ndarray, np.ndarray]: ...

@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float

@dataclass
class TranscriptionInfo:
    language: str
    language_probability: float
    duration: float

class WhisperModel:
    def __init__(
        self,
        model_size_or_path: str,
        device: str = "auto",
        compute_type: str = "default",
        local_files_only: bool = False,
        revision: str | None = None,
    ) -> None: ...
    def transcribe(
        self,
        audio: str | np.ndarray,
        language: str | None = None,
        condition_on_previous_text: bool = True,
        vad_filter: bool = False,
        hotwords: str | None = None,
    ) -> tuple[Iterable[Segment], TranscriptionInfo]: ...
    def detect_language(
        self, audio: np.ndarray | None = None
    ) -> tuple[str, float, list[tuple[str, float]]]: ...
