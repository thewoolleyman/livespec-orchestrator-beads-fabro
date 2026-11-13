"""Whether a resume of a merged pull request takes the proof-only arm."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_parking_record import (
    PARKING_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["may_be_proof_only", "proof_only_parking_record", "proof_only_resume"]

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
    return (
        proof_only_parking_record(
            item=item, pull_request_state=pull_request_state, comments=comments
        )
        is not None
    )


def proof_only_parking_record(
    *,
    item: WorkItem,
    pull_request_state: str | None,
    comments: tuple[WorkItemComment, ...] | str,
) -> str | None:
    """The identity of the acceptance park that authorizes the arm, or `None`.

    The arm's provenance names the parking record that authorized it, so the
    admission answers WHICH record rather than only whether one exists. A comment
    is identified by its ledger id, and by its own text when the ledger gave it no
    id, so the journal can still name a record a store did not number.
    """
    if not may_be_proof_only(item=item, pull_request_state=pull_request_state):
        return None
    if not isinstance(comments, tuple):
        return None
    current = next(
        (
            comment
            for comment in reversed(comments)
            if comment.text.startswith(PARKING_RECORD_TITLE)
        ),
        None,
    )
    if current is None or not current.text.startswith(_NEEDS_ATTENTION_PARK + _PROOF_EVIDENCE_LEG):
        return None
    return current.comment_id or current.text


def may_be_proof_only(*, item: WorkItem, pull_request_state: str | None) -> bool:
    """Whether the acceptance parking comments can matter, so are worth reading."""
    return item.status == "acceptance" and pull_request_state == _MERGED_STATE
