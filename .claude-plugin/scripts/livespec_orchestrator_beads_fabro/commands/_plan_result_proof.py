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
    record = _verified_record(records=records, build=target.build)
    if record is None:
        return _unmet(
            repository=repository,
            target=target,
            pull_request=pull_request,
            records=records,
            now=now,
            detail=(
                f"no verified Proof of Done record on pull request #{pull_request}"
                f" names build {target.build}"
            ),
        )
    unreproduced = tuple(
        one for one in target.assertions if record.reproduced(assertion=one) is not True
    )
    if unreproduced:
        return _unmet(
            repository=repository,
            target=target,
            pull_request=pull_request,
            records=records,
            now=now,
            detail=(
                f"the {record.verdict} record {record.url} does not list"
                f" {len(unreproduced)} of the {len(target.assertions)} requested"
                " assertion(s) as reproduced"
            ),
        )
    return satisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_PROOF_RECORD,
        now=now,
        evidence=f"proof record {record.url} verdict {record.verdict} build {target.build}",
        detail=(
            f"the {record.verdict} Proof of Done record on pull request #{pull_request}"
            f" names build {target.build} and lists all {len(target.assertions)}"
            " requested assertion(s) as reproduced"
        ),
    )


def _unmet(
    *,
    repository: ResultRepository,
    target: VerifiedProofTarget,
    pull_request: int,
    records: Sequence[ProofRecord],
    now: str,
    detail: str,
) -> ResultObservation:
    """The unmet reading of a pull request whose records WERE read.

    One constructor for both unmet arms, because the evidence identity is the same
    in each — the records that were read — and only the reason differs. Splitting
    it would let the two arms cite different evidence for one reading.
    """
    return unsatisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_PROOF_RECORD,
        now=now,
        evidence=f"{len(records)} Proof of Done record(s) on pull request #{pull_request}",
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


def _verified_record(*, records: Sequence[ProofRecord], build: str) -> ProofRecord | None:
    """The newest verified-class record naming the requested build identity.

    Newest wins because the records arrive in the forge's own chronological order
    and a later replay supersedes an earlier one. The build filter is applied
    BEFORE the choice rather than after it, so a newer record naming a different
    build does not shadow an older one that genuinely covers the requested build.
    """
    for record in reversed(tuple(records)):
        if record.verdict not in VERIFIED_PROOF_VERDICTS:
            continue
        identity = build_identity_in(body=record.body)
        if identity is not None and identity.containment_ref == build:
            return record
    return None
