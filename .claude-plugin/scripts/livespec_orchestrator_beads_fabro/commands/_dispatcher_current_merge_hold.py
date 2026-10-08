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

from typing import TYPE_CHECKING, Literal

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

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView

__all__: list[str] = [
    "MERGE_HELD_STAGE",
    "CurrentMergeHold",
    "merge_held_work_item_ids",
    "merge_hold_terminal",
    "read_current_merge_hold",
]

# What the host's merge-confirmation boundary believes about one item's hold RIGHT
# NOW. `unreadable` is a first-class answer rather than an error, because both seams
# that consume it have a defined fail-closed behaviour for it and neither may treat
# it as a release.
CurrentMergeHold = Literal["held", "unheld", "unreadable"]

# The stage a merge-held run terminates GREEN at. It is a named constant rather
# than a literal at its two sites because the second site — the post-merge
# dispositions — reads it as the ONE green outcome that has not merged, and a
# spelling that drifted between the two would silently re-arm the acceptance
# valve on unmerged work.
MERGE_HELD_STAGE = "pr"

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


def merge_hold_terminal(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    view: PrView,
    hold: CurrentMergeHold,
    run_id: str | None,
) -> DispatchOutcome | None:
    """The terminal the CURRENT merge hold puts on this run, or None to keep going.

    Keyed on the reading `confirm_pr` already acted on rather than on
    `plan.merge_hold`, so the arming decision and the terminal classification cannot
    disagree about one run. The launch snapshot cannot answer this: a hold applied
    after dispatch is absent from it, and the measured defect was both halves
    reading it (`_dispatcher_current_merge_hold`).

    A MERGED pull request is past the hold entirely and returns None, so the run
    proceeds to its ordinary post-merge path. Terminating green-with-no-merge there
    would skip the post-merge janitor and the acceptance valve on work that HAS
    merged, which is a worse outcome than the one the hold is protecting against.
    """
    if view.state == "MERGED":
        return None
    if hold != "held":
        return None
    # THE HOLD'S TERMINAL. Nothing may merge this pull request, so polling for its
    # merge could only spend the whole budget and then report a FAILURE for work that
    # succeeded. The run ends here instead, green, exactly as `contracts.md` -> "The
    # per-item merge hold" requires: green is also what reclaims the claim under the
    # ordinary green-terminal rule, so a held item holds no capacity slot while it
    # waits for a person. `merge_sha` is None because nothing merged — this is the one
    # green outcome that carries no merge, and the post-merge dispositions read that
    # from the stage rather than re-deriving the hold.
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage=MERGE_HELD_STAGE,
        pr_number=view.number,
        merge_sha=None,
        detail=(
            f"merge hold stands: PR #{view.number} is open with no auto-merge armed, "
            "and the run terminated rather than waiting for a merge no automated path "
            f"may perform. Release with `set-merge-hold:{plan.work_item_id}:off`."
        ),
        fabro_run_id=run_id,
    )
