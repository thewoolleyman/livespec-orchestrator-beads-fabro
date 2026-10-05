"""The CURRENT merge hold at the host's merge-confirmation boundary, and its terminal.

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

The reading and the TERMINAL it implies live together here because they are one
question asked twice -- "what does the hold say, and what does that do to this run" --
and the three-way terminal is only legible beside the three-valued reading it
switches on. `_dispatcher_engine_merge` owns the other half: what the reading does to
the FORGE. The terminal takes its `outcome_type` as a parameter for the reason that
module's helpers do: `_dispatcher_engine` imports this module, so a concrete
`DispatchOutcome` import here would be circular.
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

# The stage a run FAILS at when the merge-hold authority could not be read. Private
# because nothing consumes it programmatically: unlike `MERGE_HELD_STAGE`, which the
# post-merge dispositions read to recognise the one green outcome that has not
# merged, this stage exists to be READ BY A PERSON in the dispatch result. A failed
# outcome needs no second reader to behave correctly.
_MERGE_HOLD_AUTHORITY_STAGE = "merge-hold-authority"

# The stage a run FAILS at when the item IS held and the pull request still carries
# an auto-merge request after this host tried to remove it. Private for the same
# reason as the stage above: it exists to be read by a person in the dispatch result.
_MERGE_HOLD_UNENFORCED_STAGE = "merge-hold-unenforced"

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

    The green terminal is EARNED, not assumed: it is reached only when the
    authoritative view `confirm_pr` took after its own disarm carries no auto-merge
    request. A view that still carries one refuses instead, because the alternative
    is a dispatch result stating the hold holds about a pull request that is about
    to merge.
    """
    if view.state == "MERGED":
        return None
    if hold == "unreadable":
        # FAILING CLOSED IS TWO THINGS, and `confirm_pr` only does the first. It
        # made no forge write; falling through from here would then spend the whole
        # poll budget waiting for a merge this host had just declined to arm, and
        # report "PR did not reach MERGED within the poll budget" -- a true sentence
        # that names the pull request as the problem and never mentions the ledger.
        # The refusal is its own stage so the result an operator reads points at
        # what actually failed.
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage=_MERGE_HOLD_AUTHORITY_STAGE,
            pr_number=view.number,
            merge_sha=None,
            detail=(
                f"merge hold unreadable for {plan.work_item_id}: the ledger could not be "
                f"asked whether this item is held, so PR #{view.number} was left exactly "
                "as the run published it -- no auto-merge armed and none removed -- and "
                "the run did not wait for a merge it must not cause. The work is "
                "published and unharmed; re-run the dispatch once the tenant is "
                "reachable, or settle the hold with "
                f"`set-merge-hold:{plan.work_item_id}:on|off`."
            ),
            fabro_run_id=run_id,
        )
    if hold != "held":
        return None
    if view.auto_merge_armed:
        # THE HOLD WAS NOT ACHIEVED. `confirm_pr` disarms a held pull request it finds
        # armed, and this is the AUTHORITATIVE re-read it took afterwards, still
        # carrying an auto-merge request: the forge refused the write, or accepted it
        # without effect. Returning the green terminal below would state "no
        # auto-merge armed" about a pull request that is armed, so the merge this
        # hold forbids lands on the next green check run while the dispatch result
        # reads as a success -- caught in review of this item's own pull request 2614.
        #
        # Keyed on the POST-CONDITION rather than on the disarm command's exit code,
        # because the exit code can mislead in BOTH directions: a non-zero exit whose
        # pull request is nonetheless unarmed is a hold that holds, and a zero exit
        # whose pull request is still armed is one that does not. The command's own
        # result stays in the `pr-disarm-held` journal row, which is where an operator
        # tells a refused write from an ineffective one.
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage=_MERGE_HOLD_UNENFORCED_STAGE,
            pr_number=view.number,
            merge_sha=None,
            detail=(
                f"merge hold NOT enforced for {plan.work_item_id}: PR #{view.number} "
                "still carries an auto-merge request after the host tried to remove "
                "it, so the merge this hold forbids would land on the next green "
                "check run. The run refused rather than waiting for that merge. Read "
                "the `pr-disarm-held` journal row for the disarm command's own "
                "result, then remove the request by hand with "
                f"`gh pr merge {view.number} --disable-auto`, or re-apply the valve "
                f"with `set-merge-hold:{plan.work_item_id}:on`."
            ),
            fabro_run_id=run_id,
        )
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
