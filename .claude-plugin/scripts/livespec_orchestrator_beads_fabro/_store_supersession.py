"""Projection helpers for successor-owned Beads supersession edges."""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro._beads_client import EDGE_SUPERSEDES, BeadsRecord

__all__: list[str] = ["superseded_by_from_records"]


def superseded_by_from_records(*, records: list[BeadsRecord]) -> dict[str, str]:
    """Invert successor-owned supersedes edges into duplicate-owned pointers."""
    pointers: dict[str, str] = {}
    for record in records:
        successor = cast("str", record["id"])
        raw_edges = record.get("dependencies")
        if not isinstance(raw_edges, list):
            continue
        edges = cast("list[Any]", raw_edges)
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_values = cast("dict[str, Any]", edge)
            duplicate = edge_values.get("depends_on_id")
            if edge_values.get("type") == EDGE_SUPERSEDES and isinstance(duplicate, str):
                pointers[duplicate] = successor
    return pointers
