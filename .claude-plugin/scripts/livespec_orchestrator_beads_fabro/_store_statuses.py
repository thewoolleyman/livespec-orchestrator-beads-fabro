"""Status projection helpers for the beads-backed store."""

from __future__ import annotations

from typing import get_args

from livespec_orchestrator_beads_fabro.types import WorkItemStatus

__all__: list[str] = ["ALLOWED_BEADS_STATUSES", "livespec_status_for"]


def livespec_status_for(*, status: str) -> str:
    """Map a beads status onto its livespec status (`closed` -> `done`)."""
    return "done" if status == "closed" else status


ALLOWED_BEADS_STATUSES: frozenset[str] = frozenset(
    "closed" if status == "done" else status for status in get_args(WorkItemStatus)
)
