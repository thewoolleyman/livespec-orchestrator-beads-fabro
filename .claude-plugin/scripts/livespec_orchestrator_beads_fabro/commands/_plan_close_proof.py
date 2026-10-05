"""The `plan_close_proof` conformance verdict: the archive proof leg, after the fact.

The plan-record conformance clause of `SPECIFICATION/contracts.md` (v115) states
the whole rule: "`plan_close_proof` (error): an epic whose `plan_slug` names a
live or archived directory, whose close timestamp is later than 2026-10-04 (the
ratification date of the proof leg — the date of the history version that
introduced it), carries no `verified` plan Proof of Done record on its timeline
(the archive gate's third leg, made visible after the fact). An epic closed on or
before that date is out of this check's scope and MUST NOT be reported by it."

WHY THIS ASKS LESS THAN THE ARCHIVE GATE DOES, which is the design rather than an
omission. The gate (`_plan_proof_leg`) decides whether every plan assertion is
PROVED: it reads the carrier-map recency floor, the capture ordering, the release
identity and the independence rule. This check asks only whether a `verified`
record EXISTS. It is a retrospective visibility check over epics that are already
closed, so an epic it reports needs a human to look — and a check that re-ran the
whole leg would report the same epics plus a tail of records whose rejection is
unactionable after the fact, which is how a visibility check comes to be ignored.

WHY AN UNREADABLE CLOSE INSTANT IS IN SCOPE. The scope rule needs the close
timestamp, and a `bd` record is `omitempty`-sparse: a field is omitted at its ZERO
value, and a close instant has none, so a CLOSED record missing `closed_at` is an
anomaly rather than a sparse normal row. Reading it as out-of-scope would be a
gauge that passes when it cannot observe its own input — the cheapest way past
this check would be a record whose close instant nobody can read. So it is
reported, and the finding says the instant could not be read rather than claiming
the plan is unproved for a reason the record does not support.

WHY THE COMPARISON IS LEXICOGRAPHIC ON THE DATE. ISO-8601 instants sort
lexicographically, and the clause's boundary is a DATE rather than an instant:
"later than 2026-10-04" excludes every instant on that day, which `closed_at[:10]
> "2026-10-04"` expresses exactly. Parsing to a datetime would add a failure mode
— an unparseable instant — whose only honest answer is the one the leading ten
characters already give.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import VERDICT_VERIFIED
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    latest_plan_proof_entry,
    plan_proof_entries,
)

__all__: list[str] = [
    "PLAN_CLOSE_PROOF_CHECK_ID",
    "PLAN_CLOSE_PROOF_REMEDIATION",
    "PLAN_PROOF_LEG_RATIFIED_ON",
    "ClosedPlanEpic",
    "PlanCloseProofFinding",
    "plan_close_proof_findings",
]

PLAN_CLOSE_PROOF_CHECK_ID = "plan_close_proof"
# The ratification date of the archive proof leg, which is the date of the history
# version that introduced it. An epic closed on or before it is out of scope.
PLAN_PROOF_LEG_RATIFIED_ON = "2026-10-04"
PLAN_CLOSE_PROOF_REMEDIATION = (
    "the archive proof leg requires a verified plan Proof of Done record on the"
    " epic covering every plan assertion. Publish the capture and an independent"
    " replay through `dispatcher.py post-plan-record`, then re-open and re-archive"
    " the plan — or record on the epic why this closure predates the proof leg."
)

_ERROR_VERDICT = "error"
_NO_VERIFIED_RECORD = "closed plan epic carries no verified plan Proof of Done record"
_UNREADABLE_CLOSE_INSTANT = (
    "closed plan epic carries no readable close timestamp, so it cannot be shown to"
    " predate the proof leg, and carries no verified plan Proof of Done record"
)
_DATE_LENGTH = 10


@dataclass(frozen=True, kw_only=True)
class ClosedPlanEpic:
    """One closed plan epic as the check reads it.

    `plan_slug` is carried even though no verdict renders it, because it is what
    made the epic in scope — a slug naming a live or archived directory — and a
    value object that dropped it would let a caller hand in an epic whose scope it
    had decided somewhere the check cannot see.

    `comments` is the epic's whole timeline in APPEND ORDER, not a pre-filtered
    record list: the record parse is this module's to do, through the same reader
    the archive gate uses, so a check and a gate can never disagree about what
    counts as a record.
    """

    epic_id: str
    plan_slug: str
    closed_at: str
    comments: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, kw_only=True)
class PlanCloseProofFinding:
    """One reported verdict, in the shape the conformance family reports.

    The clause requires each verdict to report "the check id below, the offending
    epic id or directory path, and a remediation sentence". `event` is the fourth
    field the shipped family emits, carrying what was observed, so an operator
    reading the report does not have to infer it from the check id.
    """

    check_id: str
    subject: str
    verdict: str
    event: str
    remediation: str


def plan_close_proof_findings(
    *, epics: Sequence[ClosedPlanEpic]
) -> tuple[PlanCloseProofFinding, ...]:
    """Every in-scope epic carrying no verified plan Proof of Done record.

    `epics` is already narrowed to CLOSED epics whose `plan_slug` names a live or
    archived directory — the two conditions a caller must resolve against the
    tenant and the filesystem. What this decides is the date scope and the record
    question, which is the whole of the clause's own rule.
    """
    return tuple(
        _finding(epic=epic)
        for epic in epics
        if _in_scope(closed_at=epic.closed_at) and not _carries_verified_record(epic=epic)
    )


def _in_scope(*, closed_at: str) -> bool:
    """Whether this close instant is later than the proof leg's ratification date.

    An instant too short to carry a date is IN scope: it cannot be shown to
    predate the clause, and the honest answer to an unreadable input is not the
    one that makes the check pass.
    """
    date = closed_at.strip()[:_DATE_LENGTH]
    if len(date) < _DATE_LENGTH:
        return True
    return date > PLAN_PROOF_LEG_RATIFIED_ON


def _carries_verified_record(*, epic: ClosedPlanEpic) -> bool:
    """Whether any `verified` plan Proof of Done record sits on this timeline."""
    return (
        latest_plan_proof_entry(
            entries=plan_proof_entries(comments=epic.comments),
            verdicts=(VERDICT_VERIFIED,),
        )
        is not None
    )


def _finding(*, epic: ClosedPlanEpic) -> PlanCloseProofFinding:
    readable = len(epic.closed_at.strip()) >= _DATE_LENGTH
    return PlanCloseProofFinding(
        check_id=PLAN_CLOSE_PROOF_CHECK_ID,
        subject=epic.epic_id,
        verdict=_ERROR_VERDICT,
        event=_NO_VERIFIED_RECORD if readable else _UNREADABLE_CLOSE_INSTANT,
        remediation=PLAN_CLOSE_PROOF_REMEDIATION,
    )
