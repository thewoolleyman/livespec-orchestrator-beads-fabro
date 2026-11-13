"""The ledger-backed proof-only admission observation for one resume."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_proof_only import (
    may_be_proof_only,
    proof_only_parking_record,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["proof_only_admission"]


def proof_only_admission(
    *, repo: Path, item: WorkItem, pull_request_state: str | None
) -> str | None:
    """The current acceptance park that admits the merged proof-only arm, or `None`."""
    if not may_be_proof_only(item=item, pull_request_state=pull_request_state):
        return None
    return proof_only_parking_record(
        item=item,
        pull_request_state=pull_request_state,
        comments=read_dispatch_comments(repo=repo, item=item),
    )
