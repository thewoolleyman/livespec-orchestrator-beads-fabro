"""The ONE item's own ledger readings a dispatch needs before it can decide.

Split out of `_dispatcher_credentials` by cohesion (bd-ib-kyeor4). That module
PROJECTS credentials and sibling clones into a sandbox overlay — its own
docstring says so — while these two read the dispatched work-item's ledger
record: the operator riders its goal brief must carry, and the raw beads labels
its per-item policy overrides ride on. Neither is a credential, neither touches
the overlay, and six modules outside that one import them.

BOTH ROUTE THEIR FAILURE AS DATA rather than raising, and the two reasons are
different. A brief assembled WITHOUT comments silently re-creates a known
finding — riders are binding scope appended after filing, and nothing in the
description or the acceptance criteria announces that any exist — so a failed
read must REFUSE the dispatch rather than proceed comment-blind. The label read
is consulted for policy OVERRIDES, where an unreadable record is the same
absence an unlabelled one is, so it answers the empty tuple for a record that
carries no labels and a refusal string only for a read that could not be taken
at all.

`_LEDGER_READ_ERRORS` moved WITH them: it is the expected-error set those two
`attempt` calls catch, and a copy left behind in the projection module would be
a second account of which beads failures are routable as data.
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
