"""Post-merge AI acceptance pass for Dispatcher completions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
    criteria_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_diff import (
    DiffResult,
    read_merged_diff,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    ChangeClassification,
    EffectiveCriteria,
    change_classification,
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    ProofLeg,
    read_proof_leg,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "NEEDS_ATTENTION_VERDICT",
    "NO_CHANGE_NEEDED_VERDICT",
    "AcceptancePassResult",
    "CriterionCheck",
    "run_acceptance_pass",
]

NEEDS_ATTENTION_VERDICT = "NEEDS_ATTENTION"
NO_CHANGE_NEEDED_VERDICT = "NO_CHANGE_NEEDED"

_GREEN_STATUS = "green"
_OBSERVED_FAILING_STATUS = "failed"
_TELEMETRY_LEG = "telemetry"
_MERGED_DIFF_LEG = "merged diff"
_EMPTY_MERGED_DIFF_LEG = "empty merged diff"
_EFFECTIVE_CRITERIA_LEG = "effective criteria"


@dataclass(frozen=True, kw_only=True)
class _TelemetryEvidence:
    """The run/telemetry leg as a tri-state, not a bare pass/fail boolean.

    `observed` separates "the pass READ the run outcome" from "the outcome the
    pass read was failing". Collapsing the two is what let an unobservable
    telemetry leg manufacture a FAIL out of absent evidence, which the
    post-merge acceptance evidence rule in `SPECIFICATION/contracts.md`
    forbids: absence of evidence is never failure evidence.
    """

    observed: bool
    passed: bool
    reason: str


@dataclass(frozen=True, kw_only=True)
class AcceptancePassResult:
    """The post-merge acceptance verdict and the inputs that produced it."""

    verdict: str
    merged_diff: str | None
    diff_reason: str
    telemetry_observed: bool
    telemetry_passed: bool
    telemetry_reason: str
    criteria: tuple[CriterionCheck, ...]
    absent_evidence: tuple[str, ...]
    classification: ChangeClassification
    proof: ProofLeg | None = None

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
            "absent_evidence": list(self.absent_evidence),
            # The classification is journaled on EVERY pass, not only when the
            # empty-diff refusal fires: an item MUST NOT be silently exempted,
            # and "silently" is decided by the record of the passes that did
            # NOT refuse just as much as by the ones that did.
            "change_classification": self.classification.as_record(),
            "diff": {
                "observed": self.merged_diff is not None,
                "bytes": 0 if self.merged_diff is None else len(self.merged_diff.encode()),
                "reason": self.diff_reason,
            },
            "criteria": {
                "observed": bool(self.criteria),
                "checks": [check.as_record() for check in self.criteria],
            },
            "telemetry": {
                "observed": self.telemetry_observed,
                "passed": self.telemetry_passed,
                "reason": self.telemetry_reason,
            },
            # Named per assertion, which the proof-evidence-leg clause requires
            # of the pass's journal record: "the evidence leg it used and the
            # record comment it read". `None` for a legacy-source item, which
            # declares no proof mode and is graded on merged-diff vocabulary.
            "proof": None if self.proof is None else self.proof.as_record(),
        }


def run_acceptance_pass(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    runner: CommandRunner | None = None,
    raw_labels: Sequence[str] = (),
) -> AcceptancePassResult:
    """Read the merged diff, judge criteria, watch telemetry, and return a verdict.

    The verdict obeys the ratified evidence rule: PASS needs every leg observed
    and passing, FAIL needs OBSERVED failing evidence, and anything the pass
    cannot observe yields NEEDS_ATTENTION rather than a manufactured judgment.

    `raw_labels` carries the item's declared ledger markers, from which the
    change-implying/change-optional classification is resolved and recorded.
    An empty sequence classifies change-implying, so a caller that cannot read
    the item's labels fails closed rather than exempting it.
    """
    active_runner = ShellCommandRunner() if runner is None else runner
    classification = change_classification(raw_labels=raw_labels)
    diff_result = read_merged_diff(repo=repo, outcome=outcome, runner=active_runner)
    telemetry = _telemetry_evidence(outcome=outcome)
    criteria = effective_criteria(item=item)
    # A non-empty `proof_modes` is exactly the condition the clause draws the line
    # on: it is populated only by the Definition of Done source, and an item with
    # modes MUST NOT be graded by merged-diff vocabulary. A legacy-source item
    # declares no mode, so it keeps the pre-v114 leg and never reaches the forge.
    proof = (
        read_proof_leg(repo=repo, criteria=criteria, outcome=outcome, runner=active_runner)
        if criteria.proof_modes
        else None
    )
    checks = (
        proof.checks
        if proof is not None
        else criteria_checks(
            criteria_text=criteria.text,
            merged_diff=diff_result.merged_diff,
            telemetry_passed=telemetry.passed,
        )
    )
    absent = _absent_evidence(
        diff=diff_result,
        telemetry=telemetry,
        criteria=criteria,
        proof=proof,
        classification=classification,
    )
    return AcceptancePassResult(
        verdict=_verdict(telemetry=telemetry, checks=checks, absent=absent),
        merged_diff=diff_result.merged_diff,
        diff_reason=diff_result.reason,
        telemetry_observed=telemetry.observed,
        telemetry_passed=telemetry.passed,
        telemetry_reason=telemetry.reason,
        criteria=checks,
        absent_evidence=absent,
        classification=classification,
        proof=proof,
    )


def _telemetry_evidence(*, outcome: DispatchOutcome) -> _TelemetryEvidence:
    if outcome.status == _OBSERVED_FAILING_STATUS:
        return _TelemetryEvidence(
            observed=True,
            passed=False,
            reason=f"dispatch outcome status was {outcome.status!r}",
        )
    if outcome.status != _GREEN_STATUS:
        # `blocked` (and any future non-terminal status) is a run that parked
        # rather than reported: the leg was never read, so it is unobservable.
        return _TelemetryEvidence(
            observed=False,
            passed=False,
            reason=f"dispatch outcome status was {outcome.status!r}",
        )
    if outcome.pr_number is None:
        return _TelemetryEvidence(
            observed=False, passed=False, reason="merged PR number unavailable"
        )
    if outcome.merge_sha is None:
        return _TelemetryEvidence(
            observed=True,
            passed=True,
            reason="green merged dispatch with PR; merge sha unavailable",
        )
    return _TelemetryEvidence(
        observed=True, passed=True, reason="green merged dispatch with PR and merge sha"
    )


def _absent_evidence(
    *,
    diff: DiffResult,
    telemetry: _TelemetryEvidence,
    criteria: EffectiveCriteria,
    proof: ProofLeg | None,
    classification: ChangeClassification,
) -> tuple[str, ...]:
    """Name every evidence leg the pass could not observe, in judging order.

    The criteria leg is read off the PARSE rather than off the check set, because
    the two stopped being the same thing when the proof leg arrived: a proof-graded
    item whose record evidences nothing yields zero checks from criteria that
    parsed perfectly well, and naming the criteria leg for it would report an
    ungradeable Definition of Done where the real absence is the record.
    """
    legs: list[str] = []
    if not telemetry.observed:
        legs.append(_TELEMETRY_LEG)
    if _merged_diff_leg_absent(diff=diff, classification=classification):
        # An absent merged-diff leg is named for the OBSERVATION that produced
        # it. A merge READ as changing zero files is named as the empty-diff
        # leg; a diff that was never read keeps the plain name. Both park the
        # item, and the name is the only thing downstream can tell them apart
        # by — the parked-acceptance attention item's summary names the
        # empty-diff leg from here, per the parked-acceptance arity and
        # distinguishability rule of `SPECIFICATION/contracts.md`, so a
        # zero-change merge surfaces as itself rather than as a diff nobody
        # could read.
        legs.append(_EMPTY_MERGED_DIFF_LEG if diff.empty else _MERGED_DIFF_LEG)
    if not criteria.assertions:
        legs.append(_EFFECTIVE_CRITERIA_LEG)
    if proof is not None:
        legs.extend(proof.absent_evidence)
    return tuple(legs)


def _merged_diff_leg_absent(*, diff: DiffResult, classification: ChangeClassification) -> bool:
    """Whether the merged-diff leg is unobservable or ungradeable for this item.

    A merged diff that changes zero files is the one case the item's change
    classification decides, per the empty-merged-diff refusal in the post-merge
    acceptance evidence rule of `SPECIFICATION/contracts.md`. For a
    CHANGE-IMPLYING item — the default, and the answer a missing or malformed
    marker resolves to — the leg is
    UNGRADEABLE: an empty diff carries no evidence that any change-implying
    criterion is met, so grading it would manufacture a verdict out of absent
    evidence, and naming the leg here is what makes the verdict NEEDS_ATTENTION
    rather than PASS. A CHANGE-OPTIONAL item declared no-change-expected has an
    OBSERVED diff that happens to change nothing, so its leg is present and the
    item grades on its normal path.

    Every other absent diff is classification-independent: a command that failed
    or output that is not a patch was never read at all, and no declaration makes
    an unread diff into evidence.
    """
    if diff.empty:
        return classification.change_implying
    return not diff.gradeable or diff.merged_diff is None


def _verdict(
    *,
    telemetry: _TelemetryEvidence,
    checks: tuple[CriterionCheck, ...],
    absent: tuple[str, ...],
) -> str:
    # An OBSERVED failing outcome is dispositive failing evidence and outranks
    # any leg the pass could not read; every other absent leg parks instead.
    if telemetry.observed and not telemetry.passed:
        return "FAIL"
    if absent:
        return NEEDS_ATTENTION_VERDICT
    if all(check.passed for check in checks):
        return "PASS"
    return "FAIL"
