"""The typed VERIFIED-PROOF adapter of the shared result reader.

The shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md`
makes this the one kind that is not a field comparison: "A verified-proof read
MUST validate the existing typed Proof of Done semantics, scope, build and
verdict rather than match text." Scenario 146 states the consequence as a
control — a comment saying verified cannot satisfy a typed verified proof.

SO FOUR THINGS ARE VALIDATED, AND EACH THROUGH THE EXISTING TYPED READER RATHER
THAN THROUGH THIS MODULE'S OWN STRING WORK:

- SEMANTICS. `proof_records` is the repository's own record parser. A comment that
  merely contains the word "verified" is not a record at all to it — the header
  grammar, its closed verdict vocabulary and its publishing-identity introducer
  are what separate a record from prose that happens to read like one.
- VERDICT. Only the two VERIFIED-class verdicts are evidence here. A `captured`
  record states that a proof was produced, not that anyone reproduced it, and a
  `not_reproduced` record states the opposite of the result.
- BUILD. `build_identity_in` recovers the record's own build section and
  `containment_ref` is the ref the host-leg clause checks against — the release
  tag where a release applies, else the default-branch commit. The installed
  build identifier is deliberately NOT compared, because that clause records it
  without verifying it.
- SCOPE. Every requested assertion identifier must read as reproduced. `None`
  from `reproduced` is UNEVIDENCED rather than false, and it is not satisfaction
  either: the requested scope was not established, so the result is not satisfied.

TWO LEGS GRADE THOSE FOUR, AND THEY ARE THE ACCEPTANCE SECTION'S OWN LEGS RATHER
THAN A SECOND ACCOUNT OF THEM. `host_leg_for_records` grades every HOST record — it
owns the independence rule, the newest-wins supersession rule and the containment
refusal — and `_factory_record` grades the FACTORY record on the rule that applies
to one. Neither substitutes for the other: a host replay demands a replaying
identity distinct from the capture's, while a factory verification happens inside
the run that produced the proof, so there is no second party for an independence
rule to be about.

WHY THE BUILD IS COMPARED THROUGH THE FORGE AND NOT AS A LABEL. This read used to
ask whether a record's `containment_ref` EQUALLED the requested build, and a string
comparison is a question about spelling rather than a measurement. It failed in
both directions at once: a record taken against a later release that plainly
carries the requested build was refused, and — the costly half — a record whose
build nobody could resolve was indistinguishable from one that genuinely matched,
because no part of a string comparison can fail. Asking `containment_reader` makes
an unresolvable build UNREADABLE, which the host leg already treats as a refusal
rather than as a pass, and makes a containing later build the satisfaction it
genuinely is.

WHY A SELF-REPLAY AND A RETRACTED SUCCESS ARE REFUSED HERE EVEN THOUGH THE POSTING
PRIMITIVE ALSO REFUSES ONE. For the reason the host-leg module gives: the clause
says such a record is not evidence "however it was posted", and a record reaches a
pull request by routes that primitive does not own. Before this read consulted the
host leg, both readings came back SATISFIED — the self-replay because no identity
was compared at all, and the retracted success because the newest DECIDING record
was never sought, so a `host_verified` comment kept an obligation discharged after
its own publisher had retracted it.

WHY THE SUBJECT IS RESOLVED THROUGH ITS OWN PROOF POINTER. A record lives on a
pull request, and the subject's description is where this repository already
records which pull request carried its proof. Asking the forge to search for a
record instead would make the read depend on a query whose empty answer is
indistinguishable from a subject that never had one.

WHY THE LEDGER READ COMES FIRST AND IS NOT OPTIONAL. The pointer is the only
thing that says WHICH pull request's records are this subject's. A reader that
accepted a pull-request number from the reference instead would let a caller aim
a verified-proof result at any pull request in the repository, which is the same
hole the clause closes by refusing arbitrary predicates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    build_identity_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import (
    ContainmentReader,
    containment_reader,
    host_leg_for_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT,
    HostAssertionGrade,
    HostLeg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import pointer_in
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_VERIFIED,
    VERDICT_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_LEDGER,
    SOURCE_PROOF_RECORD,
    ResultObservation,
    satisfied,
    unobservable,
    unsatisfied,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    ResultRepository,
    result_store_config,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

__all__: list[str] = [
    "VERIFIED_PROOF_VERDICTS",
    "observe_verified_proof",
]

# The record verdicts that are EVIDENCE of a reproduced assertion: the factory
# verification and the independent host replay. `captured` says a proof was
# produced rather than reproduced, and the two negative verdicts say the
# opposite of the result — none of them is a verified proof.
VERIFIED_PROOF_VERDICTS: tuple[str, ...] = (VERDICT_VERIFIED, VERDICT_HOST_VERIFIED)

_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    BeadsConnectionError,
    BeadsCommandError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

_DESCRIPTION_FIELD = "description"


@dataclass(frozen=True, kw_only=True)
class _SubjectRefusal:
    """Why the subject named no pull request, and which source could not answer.

    A VALUE rather than a bare `None`, because the four ways this step fails have
    different remedies and the clause requires the failed source named: an
    unresolvable connection and an absent proof pointer are both unobservable, but
    one is a configuration fault in the named repository and the other is a
    subject whose proof was never published. A bare `None` collapsed them.
    """

    source: str
    detail: str


def observe_verified_proof(
    *, repository: ResultRepository, target: VerifiedProofTarget, runner: CommandRunner, now: str
) -> ResultObservation:
    """Observe whether a typed verified proof covers the requested build and scope."""
    pull_request = _subject_pull_request(repository=repository, subject_id=target.subject_id)
    if isinstance(pull_request, _SubjectRefusal):
        return unobservable(
            repo=repository.name,
            target=target.identity,
            source=pull_request.source,
            now=now,
            detail=pull_request.detail,
        )
    records = read_pull_request_records(
        repo=repository.clone, pr_number=pull_request, runner=runner
    )
    if records is None:
        return unobservable(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_PROOF_RECORD,
            now=now,
            detail=(
                f"the records on pull request #{pull_request} could not be read, so"
                " whether a verified proof was published is unknown"
            ),
        )
    # The build comparison is resolved ONCE and shared by both legs. It is lazy and
    # memoized, so a record naming no build costs no forge round trip and a capture
    # and its replay naming one release cost a single comparison between them.
    contains_requested_build = containment_reader(
        repo=repository.clone, merge_sha=target.build, runner=runner
    )
    host = host_leg_for_records(
        assertions=target.assertions, records=records, contains_merge=contains_requested_build
    )
    factory = _factory_record(records=records, contains_requested_build=contains_requested_build)
    return _reading(
        read=_Read(
            repository=repository,
            target=target,
            pull_request=pull_request,
            records=tuple(records),
            now=now,
        ),
        host=host,
        factory=factory,
    )


@dataclass(frozen=True, kw_only=True)
class _Read:
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


def _reading(*, read: _Read, host: HostLeg, factory: ProofRecord | None) -> ResultObservation:
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
        if not _assertion_proven(text=one, grade=grades.get(one), factory=factory)
    )
    if not unproven:
        return _satisfied(read=read, host=host, factory=factory)
    unreadable = tuple(one for one in host.refused if NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT in one)
    if unreadable:
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


def _satisfied(*, read: _Read, host: HostLeg, factory: ProofRecord | None) -> ResultObservation:
    """The satisfied reading, citing the record the verdict actually rested on.

    The HOST record is preferred in the citation when there is one, because it is
    the stronger evidence — it cleared independence and containment — and because
    `host.verified_record` is already keyed on a grade that PASSED, so it can never
    name a record this reader refused.
    """
    record = host.verified_record or factory
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


def _unmet(*, read: _Read, detail: str) -> ResultObservation:
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


def _subject_pull_request(
    *, repository: ResultRepository, subject_id: str
) -> int | _SubjectRefusal:
    """The pull request the subject's own proof pointer names, or why it did not."""
    config = result_store_config(repository=repository)
    if config is None:
        return _SubjectRefusal(
            source=SOURCE_LEDGER,
            detail="the named repository's own configuration did not resolve a tenant connection",
        )
    read = attempt(
        action=lambda: make_beads_client(config=config).show_issue(issue_id=subject_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return _SubjectRefusal(
            source=SOURCE_LEDGER,
            detail=(
                f"the ledger read of subject {subject_id} failed:"
                f" {type(read.error).__name__}: {read.error}"
            ),
        )
    description: object = read.get(_DESCRIPTION_FIELD)
    if not isinstance(description, str):
        return _SubjectRefusal(
            source=SOURCE_LEDGER,
            detail=f"the ledger record for subject {subject_id} carries no description",
        )
    pointer = pointer_in(description=description)
    if pointer is None:
        return _SubjectRefusal(
            source=SOURCE_PROOF_RECORD,
            detail=(
                f"subject {subject_id} carries no Proof of Done pointer naming a pull"
                " request, so there is no published record to validate"
            ),
        )
    return pointer.pull_request


def _factory_record(
    *, records: Sequence[ProofRecord], contains_requested_build: ContainmentReader
) -> ProofRecord | None:
    """The newest FACTORY-verified record whose build contains the requested one.

    Newest wins because the records arrive in the forge's own chronological order
    and a later record supersedes an earlier one. The build filter is applied
    BEFORE the choice rather than after it, so a newer record naming a build that
    does not contain the requested one does not shadow an older record that does.

    CONTAINMENT, NOT A LABEL COMPARISON, and the difference is the whole repair.
    Comparing `containment_ref` to the requested build as STRINGS asks whether the
    record happens to name the same build identity, which is a question about
    spelling: a record taken against a later release that plainly carries the
    requested build was refused, and — far worse — a record whose build nobody
    could resolve was indistinguishable from one that genuinely matched, because
    neither comparison involves a measurement that can fail. Asking the forge makes
    an unresolvable build UNREADABLE, which `refusal` treats as a refusal rather
    than as a pass.

    `host_verified` is deliberately NOT admitted here. A host replay is governed by
    `host_leg`'s independence and supersession rules, and admitting one on the
    factory rule would route it past both — the exact bypass that let a self-replay
    and a retracted success satisfy this read.
    """
    for record in reversed(tuple(records)):
        if record.verdict != VERDICT_VERIFIED:
            continue
        identity = build_identity_in(body=record.body)
        ref = None if identity is None else identity.containment_ref
        if ref is not None and contains_requested_build(ref=ref) is True:
            return record
    return None
