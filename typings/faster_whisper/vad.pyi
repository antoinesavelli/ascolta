"""Hand-written stubs for the VAD names ascolta uses (faster-whisper 1.2.1, `vad.py`)."""

from dataclasses import dataclass

import numpy as np

@dataclass
class VadOptions:
    min_speech_duration_ms: int = 0
    max_speech_duration_s: float = ...
    min_silence_duration_ms: int = 2000

def get_speech_timestamps(
    audio: np.ndarray, vad_options: VadOptions | None = None, sampling_rate: int = 16000
) -> list[dict[str, int]]: ...
