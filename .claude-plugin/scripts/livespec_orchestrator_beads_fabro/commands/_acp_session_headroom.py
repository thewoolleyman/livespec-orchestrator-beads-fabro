"""The admission session-headroom filter: its reading, its floor, its coverage.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "Admission filters candidates by projected Claude
session headroom." This module owns the VALUES that clause is written in --
one reading, the floor that grades it, and the predicate that decides which
candidate the grade applies to. Nothing here reads a credential, reaches a
provider or writes a journal; `_dispatcher_session_headroom_io` takes the
reading and `_dispatcher_session_headroom_records` writes what was decided.

THE READING IS A VALUE, NOT A READER, and that is what makes "one assessment
per distinct projected credential per admission evaluation" a property of the
type rather than a rule a memo has to keep. `SessionHeadroomGate` holds the ONE
reading an evaluation took together with the floor that governs it, so every
node and every candidate of that evaluation is graded against the same
observation by construction -- there is no second call that could return a
different answer, and no cache whose lifetime could outlive the evaluation and
make an ephemeral skip durable.

AN UNOBSERVABLE READING IS NOT A NUMBER, and keeping the two inhabited by
different fields is the whole safety property. The clause says missing,
malformed, out-of-range, transport-failed, authentication-failed and timed-out
readings "are unobservable and MUST be journaled as such, never coerced to a
numeric reading" -- so `utilization_percent` is `None` exactly when
`unobservable_reason` is set, and a consumer that reads the number gets `None`
rather than a plausible zero. A zero would read as FULL headroom, which is the
one wrong answer that admits the run the filter exists to hold.

WHY COVERAGE FOLLOWS THE RESOLVED AGENT ID AND NOTHING ELSE. The clause
requires coverage to "follow resolved agent provenance and actual credential
projection, never display text, a model-name prefix, or a spelling inferred
from an opaque availability or candidate key". A structured candidate carries
its resolved registry agent id on `AcpCandidate.agent_id`, which IS provenance:
it is what the agent catalog resolved, not something parsed back out of a
rendered command string. `candidate_is_covered` therefore asks that field and
asks nothing else. An arbitrary manual adapter carries no agent id and is
outside the clause's coverage in as many words.

KNOWN LIMIT, recorded rather than hidden: the clause also covers "a manual-form
candidate recognized as a built-in Claude adapter under the existing built-in
byte-equality rule". A built-in single-candidate node carries no fallback
metadata, so no chain of it is `enabled` and `resolve_acp_preflight` returns the
viable no-op verdict before any node is filtered -- this filter is never reached
for one. Reaching it would mean filtering a node that declares no chain, which
is the byte-identical no-op the fallback contract opens by guaranteeing. So the
built-in arm is UNREACHABLE here rather than unimplemented, and it becomes
reachable only together with a decision to filter such a node.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CLAUDE_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain

__all__: list[str] = [
    "UNOBSERVABLE_AUTHENTICATION",
    "UNOBSERVABLE_MALFORMED",
    "UNOBSERVABLE_MISSING",
    "UNOBSERVABLE_OUT_OF_RANGE",
    "UNOBSERVABLE_TRANSPORT",
    "SessionHeadroomGate",
    "SessionHeadroomReading",
    "any_covered_candidate",
    "candidate_is_covered",
    "classify_session_utilization",
    "credential_identity",
    "session_headroom_assessment",
    "unobservable_session_reading",
]

# The five unobservable results, as stable machine tokens so a journal line is
# greppable rather than prose-matched. They are SEPARATE values rather than one
# "unobservable" flag because they owe different operator responses: a transport
# failure is the network, an authentication failure is the credential, and a
# malformed or out-of-range figure is the provider's own payload.
UNOBSERVABLE_MISSING = "missing"
UNOBSERVABLE_MALFORMED = "malformed"
UNOBSERVABLE_OUT_OF_RANGE = "out-of-range"
UNOBSERVABLE_TRANSPORT = "transport-failed"
UNOBSERVABLE_AUTHENTICATION = "authentication-failed"

_FULL_UTILIZATION = 100
_IDENTITY_LENGTH = 16
_IDENTITY_PREFIX = "claude-oauth-"


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomReading:
    """One five-hour utilization observation of one projected credential.

    `credential_identity` is the OPAQUE non-secret identity the clause requires
    the journal to carry: a truncated digest of the exact projected token, which
    names the snapshot without being reversible to it. It is also what the
    observation is remembered BY, so a rotated credential is a different
    identity rather than a silently re-labelled reading of the old one.

    `utilization_percent` and `unobservable_reason` are mutually exclusive by
    construction, per the module docstring: exactly one of them is set.
    """

    credential_identity: str
    observed_at: str
    utilization_percent: float | None = None
    unobservable_reason: str | None = None

    @property
    def observable(self) -> bool:
        """Whether this reading carries a valid numeric utilization."""
        return self.utilization_percent is not None

    @property
    def remaining_headroom_percent(self) -> float | None:
        """`100` minus the utilization, or `None` for an unobservable reading.

        `None` is deliberately NOT zero. Zero is a real reading -- a credential
        with no allowance left -- and an unobservable one is the absence of a
        measurement; collapsing them would let a reader report "exhausted" about
        a provider nothing was heard from.
        """
        if self.utilization_percent is None:
            return None
        return _FULL_UTILIZATION - self.utilization_percent


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomGate:
    """The ONE reading and the floor governing a single admission evaluation."""

    reading: SessionHeadroomReading
    floor: int

    @property
    def skips_covered_candidates(self) -> bool:
        """Whether this evaluation's reading skips a covered candidate.

        A floor of `0` disables BOTH kinds of skip -- below-floor and
        unobservable -- while leaving the reading taken and journaled, which is
        the clause's own wording. Equality PASSES: the comparison is strictly
        below, so a credential sitting exactly on the floor is admitted.
        """
        if self.floor <= 0:
            return False
        remaining = self.reading.remaining_headroom_percent
        return remaining is None or remaining < self.floor


def credential_identity(*, token: str) -> str:
    """The opaque non-secret identity of one exact credential snapshot."""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:_IDENTITY_LENGTH]
    return f"{_IDENTITY_PREFIX}{digest}"


def unobservable_session_reading(
    *, credential_identity: str, observed_at: str, reason: str
) -> SessionHeadroomReading:
    """The reading an observation that produced no usable figure resolves to."""
    return SessionHeadroomReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        unobservable_reason=reason,
    )


def classify_session_utilization(
    *, value: object, credential_identity: str, observed_at: str
) -> SessionHeadroomReading:
    """Grade one raw utilization figure as a valid reading or as unobservable.

    `bool` is rejected BEFORE the numeric test rather than after it, because
    Python's `bool` IS an `int`: `True` would otherwise pass as a utilization of
    one percent, which is a plausible figure nobody measured.
    """
    if value is None:
        return unobservable_session_reading(
            credential_identity=credential_identity,
            observed_at=observed_at,
            reason=UNOBSERVABLE_MISSING,
        )
    if isinstance(value, bool) or not isinstance(value, int | float):
        return unobservable_session_reading(
            credential_identity=credential_identity,
            observed_at=observed_at,
            reason=UNOBSERVABLE_MALFORMED,
        )
    if not math.isfinite(value) or not 0 <= value <= _FULL_UTILIZATION:
        return unobservable_session_reading(
            credential_identity=credential_identity,
            observed_at=observed_at,
            reason=UNOBSERVABLE_OUT_OF_RANGE,
        )
    return SessionHeadroomReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        utilization_percent=float(value),
    )


def candidate_is_covered(*, candidate: AcpCandidate) -> bool:
    """Whether this candidate is covered by the session-headroom clause."""
    return candidate.agent_id == CLAUDE_AGENT_ID


def any_covered_candidate(*, chains: Mapping[str, ResolvedAcpChain]) -> bool:
    """Whether any FILTERED node of this dispatch carries a covered candidate.

    This is what keeps the usage request off the no-op path: a repository whose
    nodes render no covered candidate pays no usage request at all, so the clause
    adds no external call to a dispatch it cannot govern.
    """
    return any(chain.enabled and _chain_is_covered(chain=chain) for chain in chains.values())


def session_headroom_assessment(*, gate: SessionHeadroomGate) -> dict[str, object]:
    """The non-secret assessment fields every headroom record carries.

    ONE builder, so the reading record, the selection record and the containment
    refusal cannot disagree about what was observed. It carries the identity, the
    two percentages or the explicit unobservable result, the observation time and
    the governing floor -- and deliberately NO credential value and NO raw
    provider response, which the clause forbids in as many words.
    """
    reading = gate.reading
    return {
        "credential_identity": reading.credential_identity,
        "observed_at": reading.observed_at,
        "session_headroom_floor_percent": gate.floor,
        "utilization_percent": reading.utilization_percent,
        "remaining_headroom_percent": reading.remaining_headroom_percent,
        "unobservable": reading.unobservable_reason,
    }


def _chain_is_covered(*, chain: ResolvedAcpChain) -> bool:
    """Whether this node's chain carries a covered candidate anywhere in it."""
    ordered = (chain.primary, *chain.fallbacks)
    return any(candidate_is_covered(candidate=candidate) for candidate in ordered)
