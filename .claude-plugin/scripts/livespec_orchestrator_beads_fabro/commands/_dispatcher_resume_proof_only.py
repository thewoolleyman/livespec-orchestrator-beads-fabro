"""Whether a resume of a merged pull request takes the proof-only arm."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_parking_record import (
    PARKING_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["may_be_proof_only", "proof_only_resume"]

_MERGED_STATE = "MERGED"
_NEEDS_ATTENTION_PARK = f"{PARKING_RECORD_TITLE} — NEEDS_ATTENTION — pending: "
_PROOF_EVIDENCE_LEG = "proof of done record for "


def proof_only_resume(
    *,
    item: WorkItem,
    pull_request_state: str | None,
    comments: tuple[WorkItemComment, ...] | str,
) -> bool:
    """Whether the latest acceptance park authorizes the merged proof-only arm."""
    if not may_be_proof_only(item=item, pull_request_state=pull_request_state):
        return False
    if not isinstance(comments, tuple):
        return False
    current = next(
        (
            comment.text
            for comment in reversed(comments)
            if comment.text.startswith(PARKING_RECORD_TITLE)
        ),
        None,
    )
    return isinstance(current, str) and current.startswith(
        _NEEDS_ATTENTION_PARK + _PROOF_EVIDENCE_LEG
    )


def may_be_proof_only(*, item: WorkItem, pull_request_state: str | None) -> bool:
    """Whether the acceptance parking comments can matter, so are worth reading."""
    return item.status == "acceptance" and pull_request_state == _MERGED_STATE
