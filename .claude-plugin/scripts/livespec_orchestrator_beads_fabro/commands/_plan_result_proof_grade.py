"""The PURE grading half of the typed verified-proof read.

`_plan_result_proof` is the IO half — it resolves the subject through the ledger,
reads the pull request's records and builds the containment reader — and this
module decides WHAT those records prove. The split is the usual one in this tree,
and it runs here for a specific reason: the grading is a pure function of a record
set plus three answers about it, and a decision that reached for the forge itself
could not be exercised across every state the clause distinguishes without a
double for one. Every state below is reachable with no network and no tenant.

The two legs it grades are the ACCEPTANCE SECTION'S OWN, not a second account of
them: `host_leg_for_records` owns the host rule's independence, supersession and
containment, and `factory_leg` here owns the factory rule's attribution and the
same containment. The module docstring of `_plan_result_proof` carries why neither
substitutes for the other and why the unreadable-containment arm belongs to both.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    build_identity_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import (
    ContainmentReader,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT,
    HostAssertionGrade,
    HostLeg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_PROOF_RECORD,
    ResultObservation,
    satisfied,
    unobservable,
    unsatisfied,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget

__all__: list[str] = [
    "FactoryLeg",
    "ProofReading",
    "factory_leg",
    "grade_verified_proof",
]


@dataclass(frozen=True, kw_only=True)
class FactoryLeg:
    """The factory leg's answer: its record, or that one could not be graded.

    `unreadable` is NOT derivable from `record is None`. A leg with no attributable
    record at all is an OBSERVED absence, while a leg holding a correctly
    attributed record whose build comparison failed is an unmade measurement — and
    the clause sends those two to opposite statuses. Collapsing them is what made
    a factory candidate nobody could compare report as a confident negative.
    """

    record: ProofRecord | None
    unreadable: bool


@dataclass(frozen=True, kw_only=True)
class ProofReading:
    """The read that was performed, as one value every arm reports against.

    These five travel together because they are invariant across the four arms
    below and because the clause requires every observation of one read to agree
    about them — the repository, the target identity, the pull request the records
    came from, those records, and the instant. Threading them as five parameters
    through each arm is what lets a satisfied arm and an unobservable arm come to
    disagree about which read produced them.
    """

    repository: ResultRepository
    target: VerifiedProofTarget
    pull_request: int
    records: tuple[ProofRecord, ...]
    now: str


def grade_verified_proof(
    *, read: ProofReading, host: HostLeg, factory: FactoryLeg
) -> ResultObservation:
    """One observation from the two legs' grades, in the ONE order that is safe.

    REFUTED FIRST. An assertion a `host_not_reproduced` replay decided against is a
    measurement that stands on its own, so it settles the result whatever else the
    pull request carries — including an older factory record still claiming the
    assertion, which is exactly the retracted-proof case.

    SATISFIED SECOND, and it cannot be reached on a blinded comparison: a replay
    whose containment is unreadable is refused by `HostReplay.refusal` and a factory
    record's build is admitted by the same reader, so neither leg can pass an
    assertion without a comparison that was made and came back containing.

    UNOBSERVABLE THIRD — not first. It is asked only once the result is known not to
    be satisfied and not to be refuted, which is precisely when an unmade comparison
    could still have changed the answer. Asking it earlier would report a perfectly
    decided result as unobservable because some unrelated record on the same pull
    request named a build nobody could resolve.

    UNSATISFIED LAST, as the observed-but-unmet default: the records WERE read and
    nothing in them is evidence for the requested scope. That is a confident
    negative the reader earned, and it is reported with every refusal named so an
    operator can tell "nothing was published" from "something was published and
    rejected".
    """
    target = read.target
    grades = {one.text: one for one in host.grades}
    refuted = tuple(
        one for one in target.assertions if (grade := grades.get(one)) and grade.passed is False
    )
    if refuted:
        reasons = "; ".join(grades[one].reason for one in refuted)
        return _unmet(
            read=read,
            detail=(
                f"a published replay reports {len(refuted)} of the"
                f" {len(target.assertions)} requested assertion(s) as NOT reproduced:"
                f" {reasons}"
            ),
        )
    unproven = tuple(
        one
        for one in target.assertions
        if not _assertion_proven(text=one, grade=grades.get(one), factory=factory.record)
    )
    if not unproven:
        return _satisfied(read=read, host=host, factory=factory)
    unreadable = tuple(one for one in host.refused if NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT in one)
    if unreadable or factory.unreadable:
        return unobservable(
            repo=read.repository.name,
            target=target.identity,
            source=SOURCE_PROOF_RECORD,
            now=read.now,
            detail=(
                "whether a published replay names a build containing"
                f" {target.build} could not be read, so whether the requested"
                f" proof exists is unknown: {'; '.join(unreadable)}"
            ),
        )
    refusals = f": {'; '.join(host.refused)}" if host.refused else ""
    return _unmet(
        read=read,
        detail=(
            f"no Proof of Done record on pull request #{read.pull_request} is evidence"
            f" for {len(unproven)} of the {len(target.assertions)} requested"
            f" assertion(s) against build {target.build}{refusals}"
        ),
    )


def _assertion_proven(
    *, text: str, grade: HostAssertionGrade | None, factory: ProofRecord | None
) -> bool:
    """Whether EITHER leg proves this assertion, each by its own evidence rule.

    THE TWO RULES ARE DISTINCT AND NEITHER SUBSTITUTES FOR THE OTHER. A host replay
    passes only through `host_leg`, which demands an independent replaying identity
    and a build whose containment was read and holds. A factory record passes on the
    factory rule — a `verified` verdict naming a containing build that lists the
    assertion as reproduced — because the factory verification happens inside the run
    that produced the proof, so there is no second party for an independence rule to
    be about. Collapsing them would either impose independence on a factory record,
    which nothing can satisfy, or drop it from a host replay, which is the hole this
    read had.
    """
    if grade is not None and grade.passed is True:
        return True
    return factory is not None and factory.reproduced(assertion=text) is True


def _satisfied(*, read: ProofReading, host: HostLeg, factory: FactoryLeg) -> ResultObservation:
    """The satisfied reading, citing the record the verdict actually rested on.

    The HOST record is preferred in the citation when there is one, because it is
    the stronger evidence — it cleared independence and containment — and because
    `host.verified_record` is already keyed on a grade that PASSED, so it can never
    name a record this reader refused.
    """
    record = host.verified_record or factory.record
    url = "" if record is None else record.url
    verdict = "" if record is None else record.verdict
    target = read.target
    return satisfied(
        repo=read.repository.name,
        target=target.identity,
        source=SOURCE_PROOF_RECORD,
        now=read.now,
        evidence=f"proof record {url} verdict {verdict} build {target.build}",
        detail=(
            f"the {verdict} Proof of Done record on pull request #{read.pull_request}"
            f" names a build containing {target.build} and lists all"
            f" {len(target.assertions)} requested assertion(s) as reproduced"
        ),
    )


def _unmet(*, read: ProofReading, detail: str) -> ResultObservation:
    """The unmet reading of a pull request whose records WERE read.

    One constructor for both unmet arms, because the evidence identity is the same
    in each — the records that were read — and only the reason differs. Splitting
    it would let the two arms cite different evidence for one reading.
    """
    return unsatisfied(
        repo=read.repository.name,
        target=read.target.identity,
        source=SOURCE_PROOF_RECORD,
        now=read.now,
        evidence=(
            f"{len(read.records)} Proof of Done record(s) on pull request" f" #{read.pull_request}"
        ),
        detail=detail,
    )


def factory_leg(
    *, records: Sequence[ProofRecord], run_id: str, contains: ContainmentReader
) -> FactoryLeg:
    """The newest FACTORY-verified record this subject's own dispatch published.

    Newest wins because the records arrive in the forge's own chronological order
    and a later record supersedes an earlier one. Each filter is applied BEFORE
    the choice rather than after it, so a newer record failing one of them does
    not shadow an older record that passes all three.

    ATTRIBUTION IS THE FIRST FILTER, and it is the factory rule's own half.
    `_dispatcher_proof_evidence` states it plainly — "a record from another
    dispatch describes another tree" — and makes an unidentifiable dispatch fatal
    to attribution rather than a reason to fall back on the newest verified record
    whoever published it. This read admitted ANY `verified` record on the pull
    request, so a record belonging to a different dispatch satisfied the result.
    The anchor is the subject's own proof pointer, which records the run that
    evidenced its merge; it is the only attribution this reader has, and it is
    durable in the ledger rather than reconstructed here.

    CONTAINMENT IS A MEASUREMENT, NOT A LABEL COMPARISON. Comparing
    `containment_ref` to the requested build as STRINGS asks whether the record
    happens to name the same identity, which is a question about spelling: it
    refuses a record taken against a later release that plainly carries the
    requested build, and — far worse — makes a record whose build nobody could
    resolve indistinguishable from one that genuinely matched, because no part of
    a string comparison can fail.

    AN UNREADABLE COMPARISON IS REPORTED, NOT SWALLOWED. An attributed record
    whose containment answered `None` is carried out as `unreadable` so the
    caller can answer `unobservable`. Skipping it silently left the reading with
    no refusal to cite and it fell through to a confident negative — the host
    leg's `unobservable` arm has always existed, and this is its factory twin.

    `host_verified` is deliberately NOT admitted here. A host replay is governed by
    `host_leg`'s independence and supersession rules, and admitting one on the
    factory rule would route it past both — the exact bypass that let a self-replay
    and a retracted success satisfy this read.
    """
    unreadable = False
    for record in reversed(tuple(records)):
        if record.verdict != VERDICT_VERIFIED or record.run_id != run_id:
            continue
        identity = build_identity_in(body=record.body)
        ref = None if identity is None else identity.containment_ref
        if ref is None:
            continue
        carried = contains(ref=ref)
        if carried is True:
            return FactoryLeg(record=record, unreadable=False)
        if carried is None:
            unreadable = True
    return FactoryLeg(record=None, unreadable=unreadable)
