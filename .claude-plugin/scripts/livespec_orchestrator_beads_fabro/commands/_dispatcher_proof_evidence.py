"""The PROOF evidence leg of the post-merge acceptance pass.

The proof-evidence-leg clause of `SPECIFICATION/contracts.md` (v114) replaces
the criteria leg for every assertion that carries a proof mode: the evidence is
the `proof_verify` record of the run whose pull request merged, read FROM the
pull request, and "the pass MUST NOT apply merged-diff vocabulary matching to an
assertion that carries a proof mode". Vocabulary matching survives only for items
resolved from a legacy criteria source, which after v114 are only the items that
were already in flight — those declare NO mode, so this module is never reached
for them.

WHY AN UNEVIDENCED ASSERTION IS NOT A FAILING CHECK. `CriterionCheck` has two
states and the evidence rule needs three. An assertion the record does not
evidence is reported through `absent_evidence` rather than as a failing check,
because a failing check produces FAIL — which routes the item to rework and
consumes an `acceptance_rework_cap` attempt — while the unevidenceable-assertion
clause requires NEEDS_ATTENTION and says the attempt MUST NOT be consumed.
`AssertionEvidence` therefore carries `check: CriterionCheck | None`, and `None`
is the unevidenced third state.

WHY A HUMAN-ATTESTED ASSERTION PASSES HERE. The clause is explicit that "the
human-attested leg is graded by the `accept` valve, never by the AI pass", and
that PASS for a mixed item "requires every `factory_captured` assertion passing
and lists the human-attested assertions as pending". So the AI pass must not
block on the human leg, and it must not silently drop those assertions either.
They ride as passing checks whose reason SAYS they are pending, and
`pending_human_attested` is what stops the item closing before the human record
lands — the park is owned by the completion disposition, not by this verdict.

This module performs the ONE forge read of the records, and it is deliberately
the only one in the acceptance path: the pointer write consumes the same
`ProofLeg` rather than asking the forge again, so the record the pass graded and
the record the pointer cites can never be two different records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution import (
    MergingDispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_VERIFIED,
    ProofRecord,
    latest_proof_record,
    proof_records,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "HUMAN_ATTESTED_EVIDENCE_LEG",
    "PENDING_HUMAN_ATTESTATION_REASON",
    "PROOF_RECORD_EVIDENCE_LEG",
    "AssertionEvidence",
    "ProofLeg",
    "proof_leg",
    "read_proof_leg",
    "read_pull_request_records",
]

PROOF_RECORD_EVIDENCE_LEG = "proof of done record"
HUMAN_ATTESTED_EVIDENCE_LEG = "human-attested record"
PENDING_HUMAN_ATTESTATION_REASON = (
    "pending human attestation; graded by the accept valve, never by the AI pass"
)

_COMMENTS_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class AssertionEvidence:
    """One effective assertion, the leg that evidenced it, and the record read."""

    text: str
    proof_mode: str
    leg: str
    record_comment: str | None
    check: CriterionCheck | None

    def as_record(self) -> dict[str, object]:
        """The per-assertion journal projection the clause requires of the pass."""
        return {
            "text": self.text,
            "proof_mode": self.proof_mode,
            "evidence_leg": self.leg,
            "record_comment": self.record_comment,
            "evidenced": self.check is not None,
        }


@dataclass(frozen=True, kw_only=True)
class ProofLeg:
    """The proof leg of one acceptance pass: per assertion, plus the record read."""

    assertions: tuple[AssertionEvidence, ...]
    record: ProofRecord | None
    records: tuple[ProofRecord, ...]
    reason: str

    @property
    def checks(self) -> tuple[CriterionCheck, ...]:
        """The graded checks, in Definition of Done order."""
        return tuple(one.check for one in self.assertions if one.check is not None)

    @property
    def unevidenced(self) -> tuple[str, ...]:
        """The assertions the record evidenced neither way."""
        return tuple(one.text for one in self.assertions if one.check is None)

    @property
    def pending_human_attested(self) -> tuple[str, ...]:
        """The assertions awaiting a human-attested record, in section order."""
        return tuple(
            one.text for one in self.assertions if one.proof_mode == PROOF_MODE_HUMAN_ATTESTED
        )

    @property
    def absent_evidence(self) -> tuple[str, ...]:
        """One absent-evidence leg per unevidenced assertion, NAMING the assertion.

        Named rather than counted because the clause requires the verdict to name
        the assertion: an operator told only that "the proof leg is absent" has to
        read the whole record to find out which of five assertions it failed to
        evidence.
        """
        return tuple(f"{PROOF_RECORD_EVIDENCE_LEG} for {text!r}" for text in self.unevidenced)

    def as_record(self) -> dict[str, object]:
        """The journal projection naming, per assertion, its leg and record comment."""
        return {
            "reason": self.reason,
            "record_comment": None if self.record is None else self.record.url,
            "record_run_id": None if self.record is None else self.record.run_id,
            "record_verdict": None if self.record is None else self.record.verdict,
            "pending_human_attested": list(self.pending_human_attested),
            "assertions": [one.as_record() for one in self.assertions],
        }


def read_pull_request_records(
    *, repo: Path, pr_number: int, runner: CommandRunner
) -> tuple[ProofRecord, ...] | None:
    """Every Proof of Done record on one pull request, or `None` when unreadable.

    `None` is the UNOBSERVED answer and is deliberately distinct from an empty
    tuple: a pull request with no records is evidence that none were published,
    while a failed read is evidence of nothing at all, and the two must not
    produce the same verdict.
    """
    result = runner.run(
        argv=["gh", "pr", "view", str(pr_number), "--json", "comments"],
        cwd=repo,
        timeout_seconds=_COMMENTS_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    comments = _comments(stdout=result.stdout)
    if comments is None:
        return None
    return proof_records(comments=comments)


def read_proof_leg(
    *,
    repo: Path,
    criteria: EffectiveCriteria,
    outcome: DispatchOutcome,
    runner: CommandRunner,
    dispatch: MergingDispatch,
) -> ProofLeg:
    """Read the merging dispatch's record off the pull request and grade against it.

    `dispatch` carries every identifier a record may be stamped with and still
    belong to this merge, which the clause requires the pass to accept: the
    identifiers are resolved ONCE, by the caller, because the dispatch id lives in
    the dispatch journal and not on the outcome.
    """
    pr_number = outcome.pr_number
    if pr_number is None:
        return proof_leg(
            criteria=criteria, records=(), run_ids=(), reason="pull request number unavailable"
        )
    records = read_pull_request_records(repo=repo, pr_number=pr_number, runner=runner)
    if records is None:
        return proof_leg(
            criteria=criteria,
            records=(),
            run_ids=(),
            reason=f"pull request #{pr_number} comments unreadable",
        )
    run_ids = dispatch.run_ids
    if not run_ids:
        return proof_leg(
            criteria=criteria, records=records, run_ids=(), reason="merging run id unavailable"
        )
    return proof_leg(
        criteria=criteria,
        records=records,
        run_ids=run_ids,
        # Every accepted identifier is named, not just the one that matched: a
        # refusal is the common reading of this line, and an operator needs to see
        # which dispatch the pass was asking about to tell a stale record from an
        # unresolved dispatch.
        reason=f"pull request #{pr_number} records read for run {' or '.join(run_ids)}",
    )


def proof_leg(
    *,
    criteria: EffectiveCriteria,
    records: tuple[ProofRecord, ...],
    run_ids: tuple[str, ...],
    reason: str,
) -> ProofLeg:
    """Grade one item's assertions against the records published for its dispatch.

    `run_ids` is EMPTY only where the merging dispatch could not be identified,
    and that is deliberately fatal to attribution rather than a reason to fall
    back to the newest verified record whoever published it: a record from another
    dispatch describes another tree. The refusal is the record reader's own —
    `latest_proof_record` matches nothing against an empty set — rather than a
    guard here, so the two cannot come to disagree about what an unidentifiable
    dispatch is owed.
    """
    record = latest_proof_record(records=records, verdict=VERDICT_VERIFIED, run_ids=run_ids)
    return ProofLeg(
        assertions=tuple(
            _assertion_evidence(text=text, proof_mode=mode, record=record)
            for text, mode in zip(criteria.assertions, criteria.proof_modes, strict=True)
        ),
        record=record,
        records=tuple(records),
        reason=reason,
    )


def _assertion_evidence(
    *, text: str, proof_mode: str, record: ProofRecord | None
) -> AssertionEvidence:
    if proof_mode == PROOF_MODE_HUMAN_ATTESTED:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=HUMAN_ATTESTED_EVIDENCE_LEG,
            record_comment=None,
            check=CriterionCheck(text=text, passed=True, reason=PENDING_HUMAN_ATTESTATION_REASON),
        )
    if record is None:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=PROOF_RECORD_EVIDENCE_LEG,
            record_comment=None,
            check=None,
        )
    reproduced = record.reproduced(assertion=text)
    if reproduced is None:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=PROOF_RECORD_EVIDENCE_LEG,
            record_comment=record.url,
            check=None,
        )
    return AssertionEvidence(
        text=text,
        proof_mode=proof_mode,
        leg=PROOF_RECORD_EVIDENCE_LEG,
        record_comment=record.url,
        check=CriterionCheck(
            text=text,
            passed=reproduced,
            reason=_graded_reason(record=record, reproduced=reproduced),
        ),
    )


def _graded_reason(*, record: ProofRecord, reproduced: bool) -> str:
    listing = "reproduced" if reproduced else "not reproduced"
    return (
        f"{PROOF_RECORD_TITLE} {record.verdict} record {record.url}"
        f" lists the assertion as {listing}"
    )


def _comments(*, stdout: str) -> tuple[Mapping[str, object], ...] | None:
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    raw = cast("dict[str, object]", parsed).get("comments")
    if not isinstance(raw, list):
        return None
    entries = cast("list[object]", raw)
    return tuple(cast("Mapping[str, object]", one) for one in entries if isinstance(one, dict))
