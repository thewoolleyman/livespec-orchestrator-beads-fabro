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
    SOURCE_PROOF_RECORD,
    ResultObservation,
    satisfied,
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


def observe_verified_proof(
    *, repository: ResultRepository, target: VerifiedProofTarget, runner: CommandRunner, now: str
) -> ResultObservation | None:
    """Observe whether a typed verified proof covers the requested build and scope."""
    pull_request = _subject_pull_request(repository=repository, subject_id=target.subject_id)
    if pull_request is None:
        return None
    records = read_pull_request_records(
        repo=repository.clone, pr_number=pull_request, runner=runner
    )
    if records is None:
        return None
    record = _verified_record(records=records, build=target.build)
    if record is None:
        return None
    if not all(record.reproduced(assertion=one) is True for one in target.assertions):
        return None
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


def _subject_pull_request(*, repository: ResultRepository, subject_id: str) -> int | None:
    """The pull request the subject's own proof pointer names, or `None`."""
    config = result_store_config(repository=repository)
    if config is None:
        return None
    read = attempt(
        action=lambda: make_beads_client(config=config).show_issue(issue_id=subject_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return None
    description: object = read.get(_DESCRIPTION_FIELD)
    if not isinstance(description, str):
        return None
    pointer = pointer_in(description=description)
    if pointer is None:
        return None
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
