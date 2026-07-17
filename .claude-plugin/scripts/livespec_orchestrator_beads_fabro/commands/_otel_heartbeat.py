"""Heartbeat JSON-file persistence helpers for the OTLP receiver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = ["read_beats", "write_beats"]


def read_beats(*, path: Path) -> dict[str, float]:
    """Read a persisted heartbeat map, returning empty on malformed input."""
    if not path.is_file():
        return {}
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return {}
    raw = parse_json(text=text)
    if isinstance(raw, JsonParseFailure):
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
    written = attempt(
        action=lambda: _write_beats(path=path, beats=beats),
        exceptions=(OSError,),
    )
    if isinstance(written, AttemptFailure):
        return


def _write_beats(*, path: Path, beats: dict[str, float]) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = tmp.write_text(json.dumps(beats, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    _ = tmp.replace(path)
