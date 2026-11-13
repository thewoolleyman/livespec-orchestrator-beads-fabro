"""The ledger-backed proof-only admission observation for one resume."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_proof_only import (
    may_be_proof_only,
    proof_only_resume,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["proof_only_admission"]


def proof_only_admission(*, repo: Path, item: WorkItem, pull_request_state: str | None) -> bool:
    """Whether the current acceptance park admits the merged proof-only arm."""
    if not may_be_proof_only(item=item, pull_request_state=pull_request_state):
        return False
    return proof_only_resume(
        item=item,
        pull_request_state=pull_request_state,
        comments=read_dispatch_comments(repo=repo, item=item),
    )
