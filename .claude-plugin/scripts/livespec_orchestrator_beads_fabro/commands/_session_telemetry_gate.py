"""Rate limit for unchanged observation exports: at most once a minute.

A lifecycle CHANGE must be distinguishable immediately, while an observation
that has not changed would otherwise be re-exported on every poll and every
inventory invocation. The gate admits an observation when its signature differs
from the last admitted one for the same key, or when the interval has elapsed.

The marks persist between invocations in a small state file so the limit holds
across the separate processes an inventory poller runs as. The file is a hint
only: a damaged or absent one reads as empty, which at worst exports one
observation early, and it is bounded in size and age.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import uuid4

from livespec_orchestrator_beads_fabro.effects import attempt

__all__: list[str] = [
    "OBSERVATION_INTERVAL_SECONDS",
    "ObservationGate",
    "load_gate",
    "save_gate",
]

OBSERVATION_INTERVAL_SECONDS = 60.0
_MAX_MARKS = 512
_RETENTION_SECONDS = 3600.0
_MARK_FIELDS = 2


@dataclass(kw_only=True)
class ObservationGate:
    """Last admitted signature and instant per observation key."""

    interval_seconds: float = OBSERVATION_INTERVAL_SECONDS
    marks: dict[str, tuple[str, float]] = field(default_factory=dict)

    def admit(self, *, key: str, signature: str, now: float) -> bool:
        """Whether this observation may be exported now, recording it if so."""
        previous = self.marks.get(key)
        if previous is not None:
            seen_signature, seen_at = previous
            if seen_signature == signature and 0.0 <= now - seen_at < self.interval_seconds:
                return False
        self.marks[key] = (signature, now)
        return True


def load_gate(*, path: Path) -> ObservationGate:
    """Read the persisted marks, tolerating an absent or damaged file."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ObservationGate()
    if not isinstance(loaded, dict):
        return ObservationGate()
    marks: dict[str, tuple[str, float]] = {}
    for key, value in cast("dict[str, object]", loaded).items():
        mark = _mark(value=value)
        if mark is not None:
            marks[key] = mark
    return ObservationGate(marks=marks)


def _mark(*, value: object) -> tuple[str, float] | None:
    if not isinstance(value, list):
        return None
    fields = cast("list[object]", value)
    if len(fields) != _MARK_FIELDS:
        return None
    signature, seen_at = fields
    if not isinstance(signature, str) or isinstance(seen_at, bool):
        return None
    if not isinstance(seen_at, int | float):
        return None
    return signature, float(seen_at)


def save_gate(*, path: Path, gate: ObservationGate, now: float) -> None:
    """Persist the recent marks; a write that fails is a missed hint, not an error."""
    recent = sorted(
        (
            (key, mark)
            for key, mark in gate.marks.items()
            if 0.0 <= now - mark[1] < _RETENTION_SECONDS
        ),
        key=lambda item: item[1][1],
    )[-_MAX_MARKS:]
    body = json.dumps({key: list(mark) for key, mark in recent}, sort_keys=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"

    def write() -> None:
        _ = temporary.write_text(body + "\n", encoding="utf-8")
        _ = temporary.replace(path)

    _ = attempt(action=write, exceptions=(OSError,))
