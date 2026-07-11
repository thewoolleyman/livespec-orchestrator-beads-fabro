"""Heartbeat JSON-file persistence helpers for the OTLP receiver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

__all__: list[str] = ["read_beats", "write_beats"]


def read_beats(*, path: Path) -> dict[str, float]:
    """Read a persisted heartbeat map, returning empty on malformed input."""
    if not path.is_file():
        return {}
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: float(value)
        for key, value in cast("dict[str, object]", raw).items()
        if not isinstance(value, bool) and isinstance(value, int | float)
    }


def write_beats(*, path: Path, beats: dict[str, float]) -> None:
    """Write a heartbeat map atomically, swallowing filesystem failures."""
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = tmp.write_text(
            json.dumps(beats, separators=(",", ":"), sort_keys=True), encoding="utf-8"
        )
        _ = tmp.replace(path)
    except OSError:
        return
