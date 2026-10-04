"""The RECORD of why an acceptance pass parked an item — rendered, not written.

The parking-verdict clause of `SPECIFICATION/contracts.md` (v115) requires the
Dispatcher to record, on any item a pass leaves in `acceptance` under any policy,
"the verdict, each evidence leg with what was observed or what could not be
observed, each pending leg, and the action that would move the item". This module
DERIVES and RENDERS that record; `_dispatcher_acceptance_park` performs the park
it belongs to and writes it. The split is the usual pure-from-impure one: the
wording is a function of the pass alone, and a renderer that reached for the
ledger itself could not be exercised a leg at a time.

ONE COMMENT PER DISTINCT (VERDICT, PENDING-LEG SET). Beads comments are
APPEND-ONLY — `bd comments` offers neither an edit nor a delete verb — so a
re-run that re-stated an unchanged park would accumulate one comment per re-run
on exactly the items that are re-run most. The clause therefore says "a re-run
whose verdict and pending-leg set are unchanged appends nothing", and `key_line`
is that identity: it is the comment's FIRST line, so the idempotence test the
writer performs is a read of the comments already standing rather than a second
record of what was already written.

WHY EVERY LEG IS FLAGGED FROM THE VERDICT'S OWN ABSENT SET. Each leg's
observed/not-observed flag is read off `absent_evidence` rather than re-derived
from the pass's raw fields, because the two are not the same question and the
difference is invisible. A proof-graded item whose record evidences nothing
yields ZERO graded checks from criteria that parsed perfectly well, so a record
reporting the criteria leg from `len(result.criteria)` would tell an operator the
Definition of Done is ungradeable when the real absence is the record. Keying on
the absent set makes the comment agree with the verdict by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    EFFECTIVE_CRITERIA_LEG,
    EMPTY_MERGED_DIFF_LEG,
    MERGED_DIFF_LEG,
    TELEMETRY_LEG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    HUMAN_ATTESTED_EVIDENCE_LEG,
    PROOF_RECORD_EVIDENCE_LEG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_VERIFIED,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
        AcceptancePassResult,
    )

__all__: list[str] = [
    "PARKING_RECORD_TITLE",
    "EvidenceLeg",
    "ParkingRecord",
    "PendingLeg",
    "parking_record",
]

PARKING_RECORD_TITLE = "Acceptance parking record"
_NOTHING_PENDING = "nothing"


@dataclass(frozen=True, kw_only=True)
class EvidenceLeg:
    """One evidence leg of a pass, and what it observed or could not observe."""

    name: str
    observed: bool
    detail: str

    def render(self) -> str:
        state = "OBSERVED" if self.observed else "NOT OBSERVED"
        return f"- {self.name}: {state} — {self.detail}"


@dataclass(frozen=True, kw_only=True)
class PendingLeg:
    """One leg still pending, and the action that would move the item past it."""

    name: str
    action: str

    def render(self) -> str:
        return f"- {self.name}: {self.action}"


@dataclass(frozen=True, kw_only=True)
class ParkingRecord:
    """One park's whole record: the verdict, every leg, and what would move it."""

    item_id: str
    verdict: str
    policy: str
    legs: tuple[EvidenceLeg, ...]
    pending: tuple[PendingLeg, ...]

    @property
    def key_line(self) -> str:
        """The comment's first line, and the identity the idempotence test reads.

        It carries the verdict and the pending-leg NAMES, which is exactly the
        clause's "(verdict, pending-leg set)": two parks differing in neither are
        the same record, and two differing in either are not.
        """
        names = "; ".join(leg.name for leg in self.pending) or _NOTHING_PENDING
        return f"{PARKING_RECORD_TITLE} — {self.verdict} — pending: {names}"

    def render(self) -> str:
        """The whole comment body, keyed by `key_line`."""
        preamble = (
            f"The acceptance pass left work-item {self.item_id} resting in acceptance under"
            f" acceptance_policy {self.policy}; it disposed of nothing."
        )
        return "\n".join(
            [
                self.key_line,
                "",
                preamble,
                "",
                "Evidence legs:",
                "",
                *[leg.render() for leg in self.legs],
                "",
                "Pending, and the action that would move the item:",
                "",
                *self._pending_lines(),
            ]
        )

    def _pending_lines(self) -> list[str]:
        """The pending bullets, or the one line naming the valve when none is.

        A park with nothing pending is the ordinary `ai-then-human` / `human-only`
        PASS, and the clause still requires "the action that would move the item".
        For that park the action is a HUMAN's, not a leg's, so it is named here
        rather than left as an empty list that would read as nothing to do.
        """
        if self.pending:
            return [leg.render() for leg in self.pending]
        valve = (
            f"- nothing is pending: the human `accept:{self.item_id}` valve moves the item to"
            f" done, and `reject:{self.item_id}:rework` returns it to active."
        )
        return [valve]


def parking_record(
    *,
    item_id: str,
    policy: str,
    result: AcceptancePassResult,
    pull_request: int | None,
) -> ParkingRecord:
    """The record for one park, derived from the pass that produced it."""
    return ParkingRecord(
        item_id=item_id,
        verdict=result.verdict,
        policy=policy,
        legs=_evidence_legs(result=result),
        pending=_pending_legs(result=result, item_id=item_id, pull_request=pull_request),
    )


def _evidence_legs(*, result: AcceptancePassResult) -> tuple[EvidenceLeg, ...]:
    """Every leg the pass read, each flagged from the verdict's OWN absent set."""
    absent = frozenset(result.absent_evidence)
    criteria_observed = EFFECTIVE_CRITERIA_LEG not in absent
    legs = [
        EvidenceLeg(
            name=TELEMETRY_LEG,
            observed=TELEMETRY_LEG not in absent,
            detail=result.telemetry_reason,
        ),
        EvidenceLeg(
            name=MERGED_DIFF_LEG,
            observed=not absent & {MERGED_DIFF_LEG, EMPTY_MERGED_DIFF_LEG},
            detail=result.diff_reason,
        ),
        EvidenceLeg(
            name=EFFECTIVE_CRITERIA_LEG,
            observed=criteria_observed,
            detail=(
                f"{len(result.criteria)} assertion(s) reached a graded check"
                if criteria_observed
                else "the effective criteria parsed to no gradeable assertion"
            ),
        ),
    ]
    if result.proof is not None:
        legs.append(
            EvidenceLeg(
                name=PROOF_RECORD_EVIDENCE_LEG,
                observed=result.proof.record is not None,
                detail=result.proof.reason,
            )
        )
    return tuple(legs)


def _pending_legs(
    *, result: AcceptancePassResult, item_id: str, pull_request: int | None
) -> tuple[PendingLeg, ...]:
    """Every pending leg, in judging order, each with the action that would move it.

    The human-attested assertions ride BESIDE the absent set rather than inside
    it, because the pass grades them PASSING by design — the `accept` valve owns
    that leg — so they never appear as absent evidence and would otherwise be the
    one pending leg this record could not name.
    """
    legs = [
        PendingLeg(name=leg, action=_action(leg=leg, item_id=item_id, pull_request=pull_request))
        for leg in result.absent_evidence
    ]
    if result.proof is not None:
        legs.extend(
            PendingLeg(
                name=f"{HUMAN_ATTESTED_EVIDENCE_LEG} for {text!r}",
                action=_human_attested_action(pull_request=pull_request),
            )
            for text in result.proof.pending_human_attested
        )
    return tuple(legs)


def _action(*, leg: str, item_id: str, pull_request: int | None) -> str:
    """What would move the item past one named leg.

    Named per leg rather than as one generic "re-run the pass" line, because the
    legs fail for unrelated reasons and three of them need a repair FIRST: a
    re-run against an unrepaired item reproduces the same park exactly, and under
    this module's own idempotence rule it would not even leave a second record to
    say so.
    """
    if leg == TELEMETRY_LEG:
        return (
            "The dispatch reported no merged pull request, so the run outcome was never"
            f" read. Resolve the merge, then {_reaccept(item_id=item_id)}"
        )
    if leg == EMPTY_MERGED_DIFF_LEG:
        return (
            "The merge changed no files. Either the change did not land — re-implement the"
            " item — or it is genuinely no-change-expected, in which case declare the"
            f" change-optional marker on it and then {_reaccept(item_id=item_id)}"
        )
    if leg == MERGED_DIFF_LEG:
        return (
            "The merged diff could not be read. Confirm the merge sha resolves in a fresh"
            f" checkout, then {_reaccept(item_id=item_id)}"
        )
    if leg == EFFECTIVE_CRITERIA_LEG:
        return (
            "The item's Definition of Done parses to no gradeable assertion. Repair the"
            f" section, then {_reaccept(item_id=item_id)}"
        )
    return (
        f"Publish a {PROOF_RECORD_TITLE} record whose first line names {VERDICT_VERIFIED}"
        f" on {_pull_request_phrase(pull_request=pull_request)}, listing this assertion as"
        f" reproduced, then {_reaccept(item_id=item_id)}"
    )


def _human_attested_action(*, pull_request: int | None) -> str:
    return (
        f"Post one new comment on {_pull_request_phrase(pull_request=pull_request)} whose"
        f" first line is `{PROOF_RECORD_TITLE} — {VERDICT_HUMAN_ATTESTED} — <human identity>"
        " — <UTC timestamp>`, carrying each assertion's steps and proof; the accept valve"
        " refuses the item until that record exists."
    )


def _pull_request_phrase(*, pull_request: int | None) -> str:
    """Name the pull request, or say which one it is when the merge recorded none."""
    if pull_request is None:
        return "the pull request of the merging run"
    return f"pull request #{pull_request}"


def _reaccept(*, item_id: str) -> str:
    return (
        "re-run the acceptance pass with `dispatcher.py reconcile-merged --repo <repo>"
        f" --item {item_id} --invoker <role:name>`."
    )
