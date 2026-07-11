"""Rank metadata decoding for the beads-backed store."""

from __future__ import annotations

from typing import Any

from livespec_runtime.work_items.rank import BOTTOM_SENTINEL

__all__: list[str] = ["rank_from_metadata"]


def rank_from_metadata(*, metadata: dict[str, Any]) -> str:
    value = metadata.get("rank")
    if isinstance(value, str) and value != "":
        return value
    return BOTTOM_SENTINEL
