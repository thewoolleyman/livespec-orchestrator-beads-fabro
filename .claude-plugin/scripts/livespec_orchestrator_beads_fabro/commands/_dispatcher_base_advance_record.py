"""The DURABLE ledger record of an armed pull request the default branch overtook.

`_dispatcher_base_advance` decides the ending and renders it for the dispatch
RESULT; `_dispatcher_blocked` rests the item and writes the one-line surface
for the stream `drive` captures. Both are transient: the result is read once
and the stream scrolls away. The only thing on this tenant that outlives the
run is a COMMENT, so the v145 "Armed pull request overtaken by the default
branch" clause requires one, and requires it BEFORE the blocked transition.

THE ORDER IS THE OPPOSITE OF ITS NEAREST SIBLING, and that is the clause's
choice rather than an oversight. `_dispatcher_needs_human_cause` is written
AFTER its escalation, because the escalation owns the lifecycle write and a
record explaining a block that then failed to apply is worse than no record.
Here the clause says "Before the item's blocked transition", and the reason is
the other side of the same coin: this ending's record is the only account of
WHICH head was armed against WHICH tip, and a lifecycle write that succeeded
while the record was never attempted leaves an operator an item at
needs-human with no way to reconstruct what overtook it. Neither write
prevents the other — this one is fail-soft in every arm — so the ordering
decides only which account survives a partial failure.

WHAT THE RECORD MAY NOT CARRY. Names and figures only, per the clause: no
excerpt of forge output, no engine-authored prose, no diff. That is what makes
the two hazards `_dispatcher_needs_human_cause` has to neutralize structurally
absent here rather than handled — every value in this body is either one of
our own literals or a name that passed `is_identifier_shaped`, and an
identifier-shaped value cannot contain a template opener or a credential URL.
The opener detector still runs, fail-closed, for the reason stated at
`_detector_refusal` below.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    is_identifier_shaped,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "BASE_ADVANCED_MARKER",
    "base_advanced_comment_body",
    "record_base_advanced_after_arming",
]

BASE_ADVANCED_MARKER = "livespec-base-advanced-after-arming"

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

_UNREPORTED = "(not reported by the forge view)"


def record_base_advanced_after_arming(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Append the durable record for an overtaken-arming ending, once.

    Returns without writing for any other outcome. The guard is the TYPED
    `base_advanced` field rather than a match on the detail prose or on the
    `blocked` status alone: every Fabro human-gate terminal is also `blocked`,
    and this record describes none of them.

    EVERY FAILURE ARM IS JOURNALED AND NONE IS RAISED. The clause says a
    comment that fails the detector, or that cannot be written, MUST NOT
    prevent the blocked transition — the lifecycle write that matters is
    `_dispatcher_blocked`'s and has its own error arm, so losing this record
    costs an operator the durable account and is not worth converting into a
    second failure after the dispatch has already ended.
    """
    measured = outcome.base_advanced
    if measured is None:
        return
    body = base_advanced_comment_body(
        work_item_id=outcome.work_item_id,
        run_id=outcome.fabro_run_id,
        factory=measured.factory,
        pr_number=outcome.pr_number,
        pr_head=measured.pr_head,
        default_branch_tip=measured.default_branch_tip,
    )
    refusal = _detector_refusal(body=body)
    if refusal is not None:
        journal.append(
            record={
                "stage": "base-advanced-after-arming-refused",
                "work_item_id": item.id,
                "reason": refusal,
            }
        )
        return
    written = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=body,
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(written, AttemptFailure):
        journal.append(
            record={
                "stage": "base-advanced-after-arming-error",
                "work_item_id": item.id,
                "reason": type(written.error).__name__,
            }
        )
        return
    journal.append(
        record={
            "stage": "base-advanced-after-arming-record",
            "work_item_id": item.id,
            "pr_number": outcome.pr_number,
        }
    )


def base_advanced_comment_body(
    *,
    work_item_id: str,
    run_id: str | None,
    factory: str,
    pr_number: int | None,
    pr_head: str | None,
    default_branch_tip: str | None,
) -> str:
    """Render the record. PURE, so every claim it makes is testable in isolation.

    EACH NAME IS GRADED THREE WAYS, not two. A name present and
    identifier-shaped is rendered; one present but NOT identifier-shaped is
    left out and counted, which is what the clause requires; one the forge view
    never reported is stated as unreported and NOT counted. Collapsing the
    last two would make the comment assert something false about the shape of
    a value nobody read — and the two have different remedies, since an
    unpassable name is a naming fault in the dispatch while an unreported one
    is a forge reading that did not come back.
    """
    rendered: list[str] = []
    left_out = 0
    for label, value in (
        ("run id", run_id),
        ("factory", factory),
        ("pull request head", pr_head),
        ("default branch tip", default_branch_tip),
    ):
        if value is None:
            rendered.append(f"{label}: {_UNREPORTED}")
            continue
        if not is_identifier_shaped(value=value):
            left_out += 1
            continue
        rendered.append(f"{label}: {value}")
    lines = [
        BASE_ADVANCED_MARKER,
        "",
        f"work-item: {work_item_id}",
        f"pull request: {_pr_number_line(pr_number=pr_number)}",
        *rendered,
        "",
        f"{left_out} names were left out for not being identifier-shaped.",
        "",
        _DECISION,
    ]
    return "\n".join(lines)


# The one thing a reader has to DO, and the one thing they must not. The
# recovery chain is repeated from the outcome detail on purpose: this record
# outlives the dispatch result, so a reader who finds only the comment must
# still be able to act on it.
_DECISION = (
    "decision: the arming can no longer merge the head a proof record names, and no agent "
    "asked anything, so no answer is owed. The pull request is left armed and standing — do "
    "NOT disarm, close or rebase it by hand; the resumed run's pr_refresh disarms it before "
    "refreshing. Release the item with `resolve-blocked:<work-item>:ready`, then `resume "
    "--item <work-item>`, substituting the work-item named above."
)


def _pr_number_line(*, pr_number: int | None) -> str:
    """A figure, or the statement that the ending recorded none.

    Rendered rather than omitted for the same reason an unreported name is:
    an absent line is what a record written by a build predating this field
    looks like, so a reader could not tell "no pull request was named" from
    "this record never carried the key".
    """
    if pr_number is None:
        return _UNREPORTED
    return str(pr_number)


def _detector_refusal(*, body: str) -> str | None:
    """The shared template-opener detector, run fail-closed before the write.

    NO BODY THIS RENDERER BUILDS CAN FAIL IT, and the guard is worth having
    anyway. Every interpolated value is either one of our own literals or a
    name that passed `is_identifier_shaped`, whose byte set excludes `{`, so
    the detector is unreachable from the input side today. What it stands
    between is a FUTURE renderer change and a comment carrying an opener —
    which would make every later dispatch of this item refuse at the goal
    preflight, permanently, because `bd comments` offers neither an edit nor a
    delete verb. A guard against an irreversible outcome is cheap at the price
    of being redundant.
    """
    findings = minijinja_openers_in_text(source=BASE_ADVANCED_MARKER, text=body)
    if not findings:
        return None
    return f"template opener present: {', '.join(finding.opener for finding in findings)}"
