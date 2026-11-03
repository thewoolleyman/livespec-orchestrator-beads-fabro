"""Classify a credential-use guard terminal without recasting it as failure.

The sandbox guard is the only actor that can tell whether a coding agent was
refused before launch or stopped while running.  It emits one of the stable
markers below; this host-side reader turns that observation into the journal
cause used by the export-then-terminate disposition.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline_record import (
    KILLED_MID_NODE_CAUSE,
    LAUNCH_REFUSED_CAUSE,
    QUEUE_EXCEEDED_CAUSE,
)

__all__: list[str] = [
    "KILLED_MID_NODE_MARKER",
    "LAUNCH_REFUSED_MARKER",
    "QUEUE_EXCEEDED_MARKER",
    "deadline_cause_from_guard_output",
]

QUEUE_EXCEEDED_MARKER = "LIVESPEC_CREDENTIAL_DEADLINE_QUEUE_EXCEEDED"
LAUNCH_REFUSED_MARKER = "LIVESPEC_CREDENTIAL_DEADLINE_LAUNCH_REFUSED"
KILLED_MID_NODE_MARKER = "LIVESPEC_CREDENTIAL_DEADLINE_KILLED_MID_NODE"

_MARKER_CAUSES = {
    QUEUE_EXCEEDED_MARKER: QUEUE_EXCEEDED_CAUSE,
    LAUNCH_REFUSED_MARKER: LAUNCH_REFUSED_CAUSE,
    KILLED_MID_NODE_MARKER: KILLED_MID_NODE_CAUSE,
}


def deadline_cause_from_guard_output(*, text: str) -> str | None:
    """Return the sole deadline cause the guard recorded, or no deadline cause.

    A run can contain ordinary failures beside guard text, but it cannot carry
    two deadline endings: accepting a mixed or duplicated marker would make the
    durable record invent a cause.  The caller consequently leaves those
    ambiguous outputs on the ordinary failure route for investigation.
    """
    causes = {cause for marker, cause in _MARKER_CAUSES.items() if marker in text}
    return next(iter(causes)) if len(causes) == 1 else None
