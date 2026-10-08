"""What the shared authoritative result reader answers with.

The shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md`
requires the reader to return `satisfied`, `unsatisfied`, or `unobservable`,
"together with target identity, UTC observation time, and source evidence
identity (ledger comment/version, forge state/timestamp, proof record, or Git
object)". This module is that answer, and the three constructors are the only way
to build one.

WHY CONSTRUCTORS RATHER THAN A BARE DATACLASS. Every arm of every adapter has to
report the same four facts, and an adapter that assembled the value itself would
eventually omit one on the arm it cared least about. The clause's own emphasis is
that an observation failure must NOT read as satisfaction or as a confident
negative, so the arm an author cares least about is exactly the one an operator
reads during an incident.

WHY `source` AND `evidence` ARE SEPARATE FIELDS. `source` names WHERE the reader
looked — the ledger, the forge, a proof record, a Git object — and `evidence`
names WHICH artifact it found there. The clause needs both independently: a
bounded read failure "MUST name the failed source" while having no evidence to
cite, so an observation that folded the two together could not report a failure
without inventing evidence for it.

WHY `outstanding` IS A PROPERTY HERE AND NOT A CALLER'S CONJUNCTION. The clause
says a bounded read failure leaves the obligation outstanding, and that an
unobservable result preserves the budget and refuses any transition claiming
completion. Both callers therefore ask the same question, and the honest form of
it is "is this anything other than satisfied" — never "is this unsatisfied",
which an unobservable reading would answer FALSE while leaving the obligation
very much outstanding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__: list[str] = [
    "OBSERVATION_SATISFIED",
    "OBSERVATION_UNSATISFIED",
    "SOURCE_FORGE",
    "SOURCE_GIT_OBJECT",
    "SOURCE_LEDGER",
    "SOURCE_PROOF_RECORD",
    "SOURCE_REFERENCE",
    "SOURCE_REPOSITORY_RESOLUTION",
    "ResultObservation",
    "satisfied",
    "unsatisfied",
]

OBSERVATION_SATISFIED = "satisfied"
OBSERVATION_UNSATISFIED = "unsatisfied"

# The sources the clause enumerates, plus the two the reader itself can fail at
# before any of them is reached. A reference that will not parse and a repository
# that will not resolve are both named sources here rather than reported as a
# generic fault, because the clause requires the FAILED source to be named and
# "the ledger" would be a false attribution for a read that never happened.
SOURCE_LEDGER = "ledger"
SOURCE_FORGE = "forge"
SOURCE_PROOF_RECORD = "proof record"
SOURCE_GIT_OBJECT = "git object"
SOURCE_REFERENCE = "result reference"
SOURCE_REPOSITORY_RESOLUTION = "repository resolution"


@dataclass(frozen=True, kw_only=True)
class ResultObservation:
    """One reading of one required result, with everything the clause requires.

    `evidence` is the source evidence identity — the ledger comment, the forge
    state and timestamp, the proof record, or the Git object the reading rests on.
    `detail` is the sentence an operator reads; it never substitutes for the
    fields beside it.
    """

    status: Literal["satisfied", "unsatisfied"]
    repo: str
    target: str
    source: str
    observed_at: str
    evidence: str
    detail: str

    @property
    def outstanding(self) -> bool:
        """Whether the obligation this result tracks remains outstanding."""
        return self.status != OBSERVATION_SATISFIED


def satisfied(
    *, repo: str, target: str, source: str, now: str, evidence: str, detail: str
) -> ResultObservation:
    """The requested target was observed, through its named source, as fulfilled."""
    return ResultObservation(
        status="satisfied",
        repo=repo,
        target=target,
        source=source,
        observed_at=now,
        evidence=evidence,
        detail=detail,
    )


def unsatisfied(
    *, repo: str, target: str, source: str, now: str, evidence: str, detail: str
) -> ResultObservation:
    """The requested target was observed, through its named source, as UNMET.

    A confident negative, and it is earned rather than defaulted: it is returned
    only on an arm that READ its source and found the target wanting. The clause
    forbids an observation failure becoming "a confident negative", so an arm that
    could not read answers `unobservable` instead — and an unsatisfied reading
    still carries its evidence, because what WAS observed is the only thing that
    distinguishes a target that has not moved from an instrument pointed elsewhere.
    """
    return ResultObservation(
        status="unsatisfied",
        repo=repo,
        target=target,
        source=source,
        observed_at=now,
        evidence=evidence,
        detail=detail,
    )
