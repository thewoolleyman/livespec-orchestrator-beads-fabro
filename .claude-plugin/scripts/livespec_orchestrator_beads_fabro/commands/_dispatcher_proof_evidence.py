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

WHY A HOST-CAPTURED ASSERTION TAKES THAT SHAPE AND NOT THE UNEVIDENCED ONE. The
v115 host-captured leg says the same thing about the other mode: PASS "requires
every `factory_captured` assertion passing and every `host_captured` assertion
either passing from a `host_verified` record or pending", and "with no host record
that is evidence the assertion is PENDING: the pass lists it as pending the host
leg, the item rests in `acceptance` under every policy, and no
`acceptance_rework_cap` attempt is consumed". Routing it through `absent_evidence`
instead — which is where a mode this module does not recognise lands — yields
NEEDS_ATTENTION on a run whose factory leg is green, and a park whose record
reports the merging run's `verified` record as the missing thing when that record
exists and was read. The two pending modes therefore share ONE table: each is a leg
the AI pass does not grade, and the only thing that differs is which record the
operator owes.

HOW THE HOST LEG DECIDES, now that it can. The two pending modes no longer behave
identically: a `human_attested` assertion is still graded by the `accept` valve and
never here, but a `host_captured` one is graded HERE, from the records on the pull
request, because "the acceptance pass MUST judge a `host_captured` assertion passing
only from a `host_verified` record ... that lists the assertion as reproduced and
names a build identity containing the merged change", and "the pass MUST verify that
containment itself". `_dispatcher_host_leg` owns that rule; this module owns the
JOIN — it supplies the records, resolves the containment through the forge, and maps
each of the rule's three dispositions onto the shape the acceptance verdict reads.

WHY A PENDING HOST ASSERTION IS STILL A PASSING CHECK. The clause makes PASS for a
mixed item require "every `factory_captured` assertion passing and every
`host_captured` assertion either passing from a `host_verified` record or pending",
so a pending host assertion must not drag the verdict down — the factory leg is green
and the run did its job. What stops the item CLOSING is `pending_host_captured`,
which the completion disposition reads, not the verdict. A FAIL is different: a
`host_not_reproduced` record that is evidence is OBSERVED failing evidence, so it
rides as a FAILING check and routes the item to rework by the ordinary FAIL route.

WHY `pending_host_captured` NARROWED, and why that matters more than it looks. It
used to list every host-captured assertion unconditionally, because none could ever
pass. It now lists only the ones still awaiting an independent replay — and that is
precisely what makes a host-captured item CLOSEABLE, because the completion
disposition's close gate reads the remaining pending legs. A reader who restored the
unconditional form would leave every host-captured item resting in `acceptance`
forever, with a verdict of PASS and a verified host record on its pull request.

WHY THE CONTAINMENT READER DEFAULTS TO NOT-CHECKED. `proof_leg` is pure and takes the
containment answer as a callable; its default answers `None` for every build, which
the host leg treats as a refusal. So a caller that forgot to supply one PARKS the
item rather than closing it on a build nothing compared — the fail-closed direction.
`read_proof_leg` is the one production caller and always supplies one — on EVERY arm
that read records at all, which is the host-only repair. The empty-identifier arm
used to return without a reader, on the reasoning that an unattributable dispatch is
owed no evidence. That reasoning holds for the FACTORY leg and is false for the host
one: `proof_leg` deliberately does not filter host records by `run_ids`, so the
factory identifiers say nothing about whether a published replay names a build
containing the merge. A host-only item therefore rested in `acceptance` for ever,
with an independent `host_verified` replay standing on its pull request, refused for
a containment comparison nobody had made — and that refusal reads IDENTICALLY to the
one a genuinely unreadable comparison earns, so nothing in the record said which had
happened.

This module performs the ONE forge read of the records, and it is deliberately
the only one in the acceptance path: the pointer write consumes the same
`ProofLeg` rather than asking the forge again, so the record the pass graded and
the record the pointer cites can never be two different records.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import (
    ContainmentReader,
    containment_reader,
    host_leg_for_records,
    unchecked_containment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    PENDING_HOST_LEG_REASON,
    HostAssertionGrade,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution import (
    MergingDispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import (
    PROOF_RECORD_EVIDENCE_LEG,
    AssertionEvidence,
    ProofLeg,
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
    "HOST_CAPTURED_EVIDENCE_LEG",
    "HUMAN_ATTESTED_EVIDENCE_LEG",
    "PENDING_HOST_LEG_REASON",
    "PENDING_HUMAN_ATTESTATION_REASON",
    "proof_leg",
    "read_proof_leg",
    "read_pull_request_records",
]

HOST_CAPTURED_EVIDENCE_LEG = "host-captured record"
HUMAN_ATTESTED_EVIDENCE_LEG = "human-attested record"
PENDING_HUMAN_ATTESTATION_REASON = (
    "pending human attestation; graded by the accept valve, never by the AI pass"
)

_COMMENTS_TIMEOUT_SECONDS = 30.0


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

    The records are read from the pull request of the LATEST MERGED RUN, which is
    where the clause puts the host leg's "a host record on an earlier pull request is
    not evidence" rule into effect: such a record is simply absent from this read.
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
    # Resolved BEFORE the identifier arm splits, because the HOST leg does not
    # depend on the factory identifiers at all: a host replay carries a session
    # identity, `proof_leg` deliberately does not filter host records by
    # `run_ids`, and so an unattributable factory dispatch says nothing about
    # whether a published replay names a build containing the merge. Returning on
    # that arm with no reader left the default "not checked" answer standing, which
    # the host leg treats as a refusal — so a host-only item whose merge named no
    # attributable run rested in `acceptance` for ever on a comparison nobody made.
    # The reader is lazy and memoized, so building it on an arm that never asks
    # about a build costs no forge round trip.
    contains_merge = containment_reader(repo=repo, merge_sha=outcome.merge_sha, runner=runner)
    if not run_ids:
        return proof_leg(
            criteria=criteria,
            records=records,
            run_ids=(),
            reason="merging run id unavailable",
            contains_merge=contains_merge,
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
        contains_merge=contains_merge,
    )


def proof_leg(
    *,
    criteria: EffectiveCriteria,
    records: tuple[ProofRecord, ...],
    run_ids: tuple[str, ...],
    reason: str,
    contains_merge: ContainmentReader = unchecked_containment,
) -> ProofLeg:
    """Grade one item's assertions against the records published for its dispatch.

    `run_ids` is EMPTY only where the merging dispatch could not be identified,
    and that is deliberately fatal to attribution rather than a reason to fall
    back to the newest verified record whoever published it: a record from another
    dispatch describes another tree. The refusal is the record reader's own —
    `latest_proof_record` matches nothing against an empty set — rather than a
    guard here, so the two cannot come to disagree about what an unidentifiable
    dispatch is owed.

    `run_ids` deliberately does NOT filter the host records. A host replay is
    published by a session on an operator host, long after the merging run has
    finished, so it carries a session identity where a factory record carries a run
    id — filtering it by the merging dispatch's identifiers would match nothing and
    hold every host-captured item pending for ever.
    """
    record = latest_proof_record(records=records, verdict=VERDICT_VERIFIED, run_ids=run_ids)
    host = host_leg_for_records(
        assertions=criteria.host_captured_assertions,
        records=records,
        contains_merge=contains_merge,
    )
    grades = {one.text: one for one in host.grades}
    return ProofLeg(
        assertions=tuple(
            _assertion_evidence(text=text, proof_mode=mode, record=record, host=grades.get(text))
            for text, mode in zip(criteria.assertions, criteria.proof_modes, strict=True)
        ),
        record=record,
        records=tuple(records),
        reason=reason,
        host=host,
    )


def _assertion_evidence(
    *, text: str, proof_mode: str, record: ProofRecord | None, host: HostAssertionGrade | None
) -> AssertionEvidence:
    if proof_mode == PROOF_MODE_HOST_CAPTURED and host is not None:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=HOST_CAPTURED_EVIDENCE_LEG,
            record_comment=host.record_comment,
            # A PENDING grade rides as a PASSING check carrying the pending reason,
            # exactly as the human leg does: the clause requires PASS for a mixed item
            # to list the host assertion as pending rather than to fail on it. A
            # DECIDED grade carries its own verdict, so a `host_not_reproduced` record
            # reaches the ordinary FAIL route.
            check=CriterionCheck(
                text=text,
                passed=True if host.passed is None else host.passed,
                reason=host.reason,
            ),
        )
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
