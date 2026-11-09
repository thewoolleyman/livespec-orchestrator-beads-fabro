"""The merge wait's ending for an armed pull request whose CI outlasted the poll budget.

The v324 "HANDED-OFF merge wait" sentences of `SPECIFICATION/contracts.md`,
exercised by Scenario 220. A run that succeeded armed auto-merge on its pull
request and the forge will merge it by itself once the required checks pass; the
merge wait's poll budget is a fixed number of attempts, and the pull request's
CI is a measured duration that can be longer. Resting such an item at
`blocked / needs-human` asks a human to do what the forge is already doing, so
the wait ENDS WITHOUT RESTING IT: the item stays `active` under its claim, the
dispatching process ends, and the Dispatcher's next stranded-claim
reconciliation pass completes the item from whatever the forge then reports.

PURE. The decision to hand off lives in `_dispatcher_engine_exhaustion`, which
holds the forge reads; this module is the typed account of one handoff and the
two renderings of it that do not touch a ledger.

THE JOURNAL ROW IS THE HANDOFF'S ONLY MACHINE-READABLE MARK. The reconciliation
pass that completes the item reads it back to learn that the item's newest
dispatch ended in a handoff rather than in a dead process, so its stage name and
its keys are a written contract between two passes and must not drift apart:
both sides spell them through the names exported here.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "HANDED_OFF_STATUS",
    "MERGE_WAIT_HANDED_OFF_STAGE",
    "MergeWaitHandedOff",
    "merge_wait_handed_off_detail",
    "merge_wait_handed_off_journal_record",
]

# The outcome status a handed-off dispatch reports. Deliberately NOT `green`:
# green means the pull request merged, and a dozen consumers (the acceptance
# valve, calibration, the self-update canary, the cost gate) act on that
# meaning. And deliberately not `blocked`, which rests the item for a human.
HANDED_OFF_STATUS = "handed-off"

# The journal stage the handoff writes, and the stage the reconciliation pass
# looks for.
MERGE_WAIT_HANDED_OFF_STAGE = "merge-wait-handed-off"


@dataclass(frozen=True, kw_only=True)
class MergeWaitHandedOff:
    """What the merge wait measured when it handed the pull request off.

    Carried as a typed field on the outcome, for the seam reason
    `BaseAdvancedAfterArming` is: the ledger comment is written by the post-run
    disposition, long after the poll that took these readings.

    `running_checks` names only checks the forge reports as REQUIRED, in a stable
    order, because a check the pull request does not require is not what the
    handoff is waiting on. `pr_head` is `None` when the view did not report one.
    """

    factory: str
    pr_head: str | None
    waited_seconds: int
    running_checks: tuple[str, ...]


def merge_wait_handed_off_detail(*, pr_number: int, waited_seconds: int) -> str:
    """The outcome detail: the cause, and that no recovery is owed.

    It says outright that nothing needs doing, because every other `merge-poll`
    ending names a recovery chain and a reader who finds none must not conclude
    that the chain was left out.
    """
    return (
        f"{MERGE_WAIT_HANDED_OFF_STAGE}: the merge wait's poll budget ended after "
        f"{waited_seconds} seconds while pull request #{pr_number} was OPEN, not in conflict, "
        "with auto-merge armed and no required check failed, so the item stays active under "
        "its claim and the Dispatcher's next stranded-claim reconciliation pass completes it "
        "from what the forge then reports; no resolve-blocked and no resume is owed."
    )


def merge_wait_handed_off_journal_record(
    *,
    work_item_id: str,
    run_id: str | None,
    pr_number: int,
    handed_off: MergeWaitHandedOff,
) -> dict[str, object]:
    """The one journal row a handoff leaves, naming everything the clause lists."""
    return {
        "stage": MERGE_WAIT_HANDED_OFF_STAGE,
        "work_item_id": work_item_id,
        "run_id": run_id,
        "pr_number": pr_number,
        "pr_head": handed_off.pr_head,
        "waited_seconds": handed_off.waited_seconds,
        "running_checks": list(handed_off.running_checks),
    }
