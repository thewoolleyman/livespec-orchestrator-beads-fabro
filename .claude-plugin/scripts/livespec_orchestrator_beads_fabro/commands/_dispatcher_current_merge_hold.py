"""The CURRENT merge hold, read at the host's merge-confirmation boundary.

`DispatchPlan.merge_hold` is a LAUNCH SNAPSHOT and must stay one. The sandbox's pr
stage reads the `merge_hold` workflow input rendered from it, the dispatch record
journals what was rendered, and a value re-derived at either of those points is how
the record and the run come to disagree about what this dispatch did.

But the host's own merge confirmation runs HOURS after that snapshot was taken, and a
maintainer setting the hold during the run is precisely the window the per-item merge
hold of `SPECIFICATION/contracts.md` exists to open. A host that armed auto-merge from
the snapshot would therefore REVERSE a hold applied after dispatch -- measured
2026-10-05 on pull request 2607, where a pr stage that correctly armed nothing was
undone by the host fallback 16 seconds later.

So the host reads the hold HERE, from the ledger authority the `set-merge-hold` valve
writes, and the reading is projected to both host seams that need it: the auto-merge
fallback and the terminal classification. This does not make the host authoritative
over the sandbox, and it is not a second hold valve -- the valve still owns the label
and its own forge write. It only stops the host from arming a merge the ledger
currently forbids.

The reading is THREE-valued because an unreadable authority is NOT a released hold. A
gauge that answered "unheld" when it could not see would convert a substrate hiccup
into the merge of work a person may have just held, and would leave a journal reading
exactly like a healthy release. Every expected failure of the read -- an unconfigured
repository, an unreachable tenant, a malformed record -- therefore lands on
`unreadable`, and the two host seams fail CLOSED on it: no forge write, and an
explicit refusal rather than a wait.

NOTHING here claims an atomic guarantee. The ledger read and the forge write are
independent, so a hold set in the gap between them is still possible; what this
removes is the host REVERSING a hold it could have seen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from livespec_orchestrator_beads_fabro._store_merge_hold import read_merge_held_work_item_ids
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "CurrentMergeHold",
    "merge_held_work_item_ids",
    "read_current_merge_hold",
]

# What the host's merge-confirmation boundary believes about one item's hold RIGHT
# NOW. `unreadable` is a first-class answer rather than an error, because both seams
# that consume it have a defined fail-closed behaviour for it and neither may treat
# it as a release.
CurrentMergeHold = Literal["held", "unheld", "unreadable"]

# The EXPECTED-error surface one hold read (`resolve_store_config` +
# `read_merge_held_work_item_ids`) can raise. The set mirrors `_ready_aging_order`'s
# dwell read, and it is enumerated rather than blanket-caught for the same reason: a
# bare `except` would also swallow a programming error here and report it as an
# unreachable tenant.
_HOLD_READ_ERRORS: tuple[type[Exception], ...] = (
    LivespecConfigUnreadableError,
    ConnectionPrefixMissingError,
    BeadsCredentialMissingError,
    BeadsConnectionError,
    BeadsTenantMissingError,
    BeadsCommandError,
    BeadsMappingError,
)


def merge_held_work_item_ids(*, repo: Path) -> frozenset[str]:
    """Every merge-held id in the tenant this repository's committed block names.

    The whole held set rather than one item's marker, because that raw label read is
    the sanctioned authority: `store._record_to_work_item` decodes labels into the
    named fields the shared `WorkItem` model declares, so the hold marker is dropped
    on the floor before any item-shaped read could see it.
    """
    return read_merge_held_work_item_ids(path=resolve_store_config(cwd=repo, work_items_arg=None))


def read_current_merge_hold(*, repo: Path, work_item_id: str) -> CurrentMergeHold:
    """Whether the ledger holds this item's merge right now, or cannot say."""
    read = attempt(
        action=lambda: merge_held_work_item_ids(repo=repo),
        exceptions=_HOLD_READ_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return "unreadable"
    return "held" if work_item_id in read else "unheld"
