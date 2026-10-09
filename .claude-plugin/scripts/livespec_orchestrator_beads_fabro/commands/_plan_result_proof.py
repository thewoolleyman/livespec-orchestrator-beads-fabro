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
refusal — and `_factory_leg` grades the FACTORY record on the rule that applies to
one. Neither substitutes for the other, and each rule has TWO halves that are easy
to implement one of:

- The HOST rule's halves are INDEPENDENCE (a replaying identity distinct from the
  capture's) and CONTAINMENT. A factory verification happens inside the run that
  produced the proof, so there is no second party for independence to be about,
  and imposing it there would refuse every factory record.
- The FACTORY rule's halves are ATTRIBUTION (the record belongs to the dispatch
  the subject's own proof pointer names) and the same CONTAINMENT. Omitting
  attribution let a `verified` record from ANOTHER dispatch satisfy the result,
  which `_dispatcher_proof_evidence` rules out in as many words: "a record from
  another dispatch describes another tree".

AND THE UNREADABLE-CONTAINMENT ARM BELONGS TO BOTH LEGS. The host leg has always
answered `unobservable` when a replay's build comparison could not be read. The
factory leg skipped such a record silently, and with no host record to carry a
refusal the reading fell through to a confident negative about a build nobody
compared — the same forbidden direction, left behind by fixing one leg only. That
is why `_FactoryLeg` carries `unreadable` as its own field rather than letting the
caller infer it from an absent record: an unattributable leg and an ungradeable one
are opposite statuses.

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

AND A RECORD'S BUILD HAS TWO THINGS TO CARRY, NOT ONE. The requested build says
which build the reference is ABOUT; the subject's recorded merge says which change
that build must CONTAIN. Checking only the first leaves a replay taken against a
release predating the merge as satisfaction — proof of a build that does not carry
the work. `_authoritative_containment` composes both into one reader, and the merge
half is VACUOUS when the subject records no merge, because "containing the merged
change" presupposes a merged change and failing closed there would make this result
permanently unobservable for every subject whose work has not closed.

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

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import (
    ContainmentReader,
    containment_reader,
    host_leg_for_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import pointer_in
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_VERIFIED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_LEDGER,
    SOURCE_PROOF_RECORD,
    ResultObservation,
    unobservable,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_proof_grade import (
    ProofReading,
    factory_leg,
    grade_verified_proof,
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
_METADATA_FIELD = "metadata"
_AUDIT_FIELD = "audit"
_MERGE_SHA_FIELD = "merge_sha"


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


@dataclass(frozen=True, kw_only=True)
class _Subject:
    """What the subject's own ledger record says about where its proof lives.

    THREE FIELDS BECAUSE THE TWO EVIDENCE RULES NEED THREE DIFFERENT THINGS, and
    reading the record once is what keeps them consistent with each other. The
    pull request says WHICH records are this subject's; the pointer's run id is
    the attribution anchor the FACTORY rule needs, since a record from another
    dispatch describes another tree; and the recorded merge is what the HOST rule
    requires a build to contain.

    `merge_sha` is `None` for a subject whose work has not closed, and that is a
    legitimate state rather than a fault — see `_authoritative_containment`.
    """

    pull_request: int
    run_id: str
    merge_sha: str | None


def observe_verified_proof(
    *, repository: ResultRepository, target: VerifiedProofTarget, runner: CommandRunner, now: str
) -> ResultObservation:
    """Observe whether a typed verified proof covers the requested build and scope."""
    subject = _subject_proof(repository=repository, subject_id=target.subject_id)
    if isinstance(subject, _SubjectRefusal):
        return unobservable(
            repo=repository.name,
            target=target.identity,
            source=subject.source,
            now=now,
            detail=subject.detail,
        )
    pull_request = subject.pull_request
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
    contains = _authoritative_containment(
        repository=repository, target=target, subject=subject, runner=runner
    )
    host = host_leg_for_records(
        assertions=target.assertions, records=records, contains_merge=contains
    )
    factory = factory_leg(records=records, run_id=subject.run_id, contains=contains)
    return grade_verified_proof(
        read=ProofReading(
            repository=repository,
            target=target,
            pull_request=pull_request,
            records=tuple(records),
            now=now,
        ),
        host=host,
        factory=factory,
    )


def _authoritative_containment(
    *,
    repository: ResultRepository,
    target: VerifiedProofTarget,
    subject: _Subject,
    runner: CommandRunner,
) -> ContainmentReader:
    """Whether a record's build carries BOTH things it has to carry.

    TWO RELATIONS, COMPOSED INTO ONE READER, because a record's build has two
    separate obligations and each alone admits a record the other rejects:

    - THE REQUESTED BUILD. The reference names a build identity, and a record
      whose build does not cover it is about other work. Comparing the two as
      LABELS is what the clause rules out, and it also refuses a record taken
      against a later release that plainly carries the requested build.
    - THE SUBJECT'S RECORDED MERGE. The host-leg clause admits a record "naming a
      build identity containing the merged change". Checking only the requested
      build leaves a replay taken against a release PREDATING the merge as
      satisfaction — proof of a build that does not carry the work.

    THE MERGE RELATION IS VACUOUS WHEN NO MERGE IS RECORDED, and that is a rule
    rather than a convenience: "containing the merged change" presupposes a merged
    change, so a subject whose work has not closed has nothing for a build to
    contain. Failing closed there would make the verified-proof result PERMANENTLY
    unobservable for every such subject — a guard that blinds the instrument it
    guards, which is the failure the requested-build relation already exists to
    avoid in the other direction.

    EITHER RELATION BEING UNREADABLE MAKES THE ANSWER UNREADABLE, never `False`.
    `host_leg` treats `None` as a refusal naming unobservable containment, so an
    unmade comparison leaves the obligation outstanding instead of convicting a
    record on a measurement nobody took.
    """
    contains_requested = containment_reader(
        repo=repository.clone, merge_sha=target.build, runner=runner
    )
    merge_sha = subject.merge_sha
    if merge_sha is None:
        return contains_requested
    contains_merge = containment_reader(repo=repository.clone, merge_sha=merge_sha, runner=runner)

    def contains_both(*, ref: str) -> bool | None:
        requested = contains_requested(ref=ref)
        merged = contains_merge(ref=ref)
        if requested is None or merged is None:
            return None
        return requested and merged

    return contains_both


def _subject_proof(*, repository: ResultRepository, subject_id: str) -> _Subject | _SubjectRefusal:
    """What the subject's ledger record says about its proof, or why it said nothing.

    ONE READ supplies all three answers — the pull request, the pointer's run id
    and the recorded merge — because they have to describe the SAME record. Two
    reads could straddle a ledger write and grade a pull request's records against
    another state's attribution.
    """
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
    return _Subject(
        pull_request=pointer.pull_request,
        run_id=pointer.run_id,
        merge_sha=_recorded_merge(record=read),
    )


def _recorded_merge(*, record: BeadsRecord) -> str | None:
    """The merge the subject's audit metadata records, or `None` when it records none.

    Read from the raw record's own nested keys rather than through the store's
    item mapping, because this adapter holds a `show_issue` payload and the
    mapping's audit parse is private to that module. The two nested reads are
    tolerant in the `omitempty`-sparse direction: a record carrying no metadata,
    no audit, or no merge is a subject whose work has not closed, which is a
    legitimate state and not a malformed one.
    """
    metadata: object = record.get(_METADATA_FIELD)
    if not isinstance(metadata, dict):
        return None
    audit: object = cast("dict[str, object]", metadata).get(_AUDIT_FIELD)
    if not isinstance(audit, dict):
        return None
    merge: object = cast("dict[str, object]", audit).get(_MERGE_SHA_FIELD)
    if not isinstance(merge, str) or merge.strip() == "":
        return None
    return merge
