"""Minimal client for the local Ollama server: chat, pin check, loaded VRAM, unload.

Depends on: the Ollama server at localhost:11434.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from ascolta.calls import StageError

URL = "http://localhost:11434"


def _call(
    path: str, payload: dict[str, Any] | None = None, timeout: float = 1800
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        URL + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result: dict[str, Any] = json.load(response)
        return result


def check_pin(name: str, digest: str) -> None:
    """Stop when the tag's weights are not the ones pinned in models.yaml."""
    live = {m["name"]: m["digest"] for m in _call("/api/tags")["models"]}.get(name)
    if live != digest:
        raise StageError(
            f"{name}: digest {(live or 'missing')[:12]} does not match the pin {digest[:12]} in models.yaml"
        )


def chat(
    model: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    keep_alive: str | int,
    fmt: dict[str, Any] | None = None,
    think: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
        "keep_alive": keep_alive,
    }
    if fmt is not None:
        payload["format"] = fmt
    if think is not None:
        payload["think"] = think
    return _call("/api/chat", payload)


def loaded_vram_gb() -> float:
    return float(sum(m.get("size_vram", 0) for m in _call("/api/ps")["models"]) / 2**30)


def unload(model: str) -> None:
    _call("/api/generate", {"model": model, "keep_alive": 0})
