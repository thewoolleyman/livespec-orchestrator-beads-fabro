"""Temporary test seam for receiver-side telemetry capture."""

from __future__ import annotations

from collections.abc import Iterable


def unique_spans(*, batches: Iterable[tuple[dict[str, object], ...]]) -> list[dict[str, object]]:
    """Return every captured span while the Red test describes deduplication."""

    return [span for spans in batches for span in spans]
