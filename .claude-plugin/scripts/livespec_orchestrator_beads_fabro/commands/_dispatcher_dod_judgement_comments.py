"""Read one work item's ledger comment bodies for a Definition-of-Done judgement.

Split out of `_dispatcher_dod_judgement_gate` by cohesion: the gate decides what a
judgement does with the comments it is handed, while this owns only the READ that
produces them, so the gate stays under its file LLOC ceiling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_rider_bound import (
    carried_comment_bodies,
    prior_claim_instant,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["item_comment_bodies", "judgement_comment_bodies"]

_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")
_LEDGER_READ_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def item_comment_bodies(*, path: StoreConfig, work_item_id: str) -> tuple[str, ...] | None:
    """One item's comment bodies oldest-first, or `None` when they cannot be read.

    `None` and the empty tuple are deliberately different answers: an item with
    no comments has no recorded verdict and must be judged, while an item whose
    sidecar could not be read is one nothing can be concluded about.
    """
    read = attempt(
        action=lambda: read_work_item_comments(path=path, work_item_id=work_item_id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return None
    return tuple(comment.text for comment in read)


def judgement_comment_bodies(
    *, path: StoreConfig, work_item_id: str, repo: Path
) -> tuple[str, ...] | None:
    """The comment bodies a judgement subject is computed from, or `None` when unreadable.

    `item_comment_bodies` less every rider the goal would not carry: the subject
    carries "only the carried riders", so a rider appended before the item's most
    recent dispatch claim that is neither standing nor stage-scoped leaves the
    digest unchanged and a cache-eligible verdict taken after that claim is reused
    without a judge. Receipts stay, because the reuse read finds the recorded
    verdict among them.

    The claim is read from `repo`'s default dispatch journal, the path every
    lifecycle reader without a namespace resolves. This is the HOST taking's bound,
    so no dispatch id is excluded: the in-run `dod_gate` subject excludes its own
    dispatch's claim and so reaches the same bound.
    """
    read = attempt(
        action=lambda: read_work_item_comments(path=path, work_item_id=work_item_id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return None
    claim_at = prior_claim_instant(
        journal_path=repo.joinpath(*_JOURNAL_SUBPATH), item_id=work_item_id
    )
    return carried_comment_bodies(comments=read, claim_at=claim_at)
