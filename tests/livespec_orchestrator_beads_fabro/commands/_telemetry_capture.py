"""Temporary test seam for receiver-side telemetry capture."""

from __future__ import annotations

import json
from collections.abc import Iterable


def unique_spans(*, batches: Iterable[tuple[dict[str, object], ...]]) -> list[dict[str, object]]:
    """Collapse retried transport batches without changing first-arrival order."""

    unique: dict[str, dict[str, object]] = {}
    for spans in batches:
        for span in spans:
            _ = unique.setdefault(json.dumps(span, sort_keys=True), span)
    return list(unique.values())
