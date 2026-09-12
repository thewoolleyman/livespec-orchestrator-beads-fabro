"""The two Ledger reads a dispatch performs before it can assemble a brief.

Split out of `_dispatcher_credentials` because they share none of its concerns: these
read the beads tenant, while everything left there projects host credentials into a run
overlay. The only thing the two halves ever shared was the module they happened to sit in.

BOTH READS REFUSE RATHER THAN DEGRADE, and for the same reason. A brief assembled without
comments, or a policy decision taken without labels, is not a smaller brief — it is a
brief that silently omits binding scope an operator added after filing. So a failed read
returns an error STRING (error-as-data, routed at its own dispatch stage) instead of an
empty tuple that would be indistinguishable from a genuinely comment-less item.

THE TWO DIFFER ON WHAT AN ABSENCE MEANS, which is why they are not one function. A failed
comments READ is a refusal; a record whose `labels` member is simply absent is not, because
beads omits any field holding its zero value, so "no labels" and "labels unreadable" are
different observations and only the second is a failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.store import (
    WorkItemComment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "read_dispatch_comments",
    "read_dispatch_labels",
]

_LEDGER_READ_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def read_dispatch_comments(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[WorkItemComment, ...] | str:
    """Read the item's ledger comments for the goal; error string on failure.

    Comments are operator riders appended after filing (e.g.
    pre-authorizations); a brief without them silently re-creates bn4
    finding (c), so a failed read REFUSES the dispatch (error-as-data,
    routed at the `ledger-comments` stage) instead of proceeding
    comment-blind.
    """
    comments = attempt(
        action=lambda: read_work_item_comments(path=store_config(repo=repo), work_item_id=item.id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(comments, AttemptFailure):
        return (
            f"ledger comments read failed for {item.id} "
            f"({type(comments.error).__name__}: {comments.error})"
        )
    return comments


def read_dispatch_labels(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[str, ...] | str:
    """Read raw beads labels that carry per-item dispatcher policy overrides."""
    record = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)).show_issue(
            issue_id=item.id
        ),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(record, AttemptFailure):
        return (
            f"ledger label read failed for {item.id} "
            f"({type(record.error).__name__}: {record.error})"
        )
    labels = record.get("labels")
    if not isinstance(labels, list):
        return ()
    raw_labels = cast("list[object]", labels)
    return tuple(label for label in raw_labels if isinstance(label, str))
