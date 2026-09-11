"""The CLOSED decision: is this candidate failure an availability failure?

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" gives this decision a fixed shape, and the ORDER of the steps
below is the contract's own order rather than an implementation
convenience:

1. The non-eligible classes "are non-eligible before configured matching
   and MUST terminate with their original identity". They are checked
   first so no configured literal can ever claim one of them.
2. "A mere pre-turn failure is not provider evidence." A failure before
   any turn, with nothing on any readable field, is the provider saying
   nothing at all.
3. A candidate with no explicit identity cannot be classified typed: the
   contract keeps an identity-less no-fallback legacy adapter on "the
   conservative legacy posture", covered by legacy provider records and
   minting them through v107 cause-text attribution. A typed hold needs a
   `(availability_key, candidate_key)` to be scoped by, and inventing one
   would mint an entitlement nobody declared.
4. "Structured machine codes take precedence." A matching machine code
   settles it and text signatures are not consulted.
5. "If distinct signatures nevertheless match one runtime diagnostic with
   different cause/scope/key dispositions, the failure is non-eligible
   and surfaced as ambiguous, and it creates no hold; runtime first-match
   choice is forbidden."

PRECEDENCE IS A FILTER, NOT A SORT, and that distinction is load-bearing
for step 5. Taking the first machine-code match would resolve an
ambiguity by ordering, which is the forbidden choice; taking the SET of
machine-code matches and then applying the ambiguity rule to it keeps two
disagreeing codes refusing, exactly as two disagreeing literals do.

WHAT THIS DOES NOT DO. It mints nothing, reads no journal and reaches no
provider: it returns a verdict. `_acp_hold_records` turns an eligible
verdict into an observation, and only when the caller can name evidence
of an actual attempt. Preflight filtering, admission, and the runtime
transition are S3 and later, and are deliberately absent.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    effective_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_matching import (
    MACHINE_CODE_SOURCE,
    generic_status_reason,
    signature_discriminates,
    signature_matches,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import (
    AcpFailureSignal,
    non_eligible_reason,
)

__all__: list[str] = [
    "CANDIDATE_SCOPE",
    "DOMAIN_SCOPE",
    "AcpAvailabilityFailure",
    "AcpNonEligibleFailure",
    "classify_acp_failure",
]

DOMAIN_SCOPE = "availability-domain"
CANDIDATE_SCOPE = "candidate"


@dataclass(frozen=True, kw_only=True)
class AcpAvailabilityFailure:
    """An ELIGIBLE typed availability failure, already scoped to its hold key.

    The hold key is resolved here rather than left to the record writer
    because resolving it is part of deciding: a domain signature's
    optional `hold_key` override is what the ambiguity rule compares, so
    two signatures agreeing on cause and scope but disagreeing on the
    override are ambiguous, and that comparison can only happen where the
    override is applied.
    """

    cause: str
    scope: str
    hold_key: str
    availability_key: str
    candidate_key: str | None
    source: str


@dataclass(frozen=True, kw_only=True)
class AcpNonEligibleFailure:
    """A failure that mints no hold, carrying WHY and its untouched identity.

    `original_identity` is the contract's "MUST terminate with their
    original identity": the caller re-raises the failure it already had
    rather than a provider cause that was never measured.
    """

    reason: str
    original_identity: str


def classify_acp_failure(
    *, signal: AcpFailureSignal, candidate: AcpCandidate, builtin: bool = False
) -> AcpAvailabilityFailure | AcpNonEligibleFailure:
    """Decide whether one candidate attempt failed on provider availability."""
    guard = non_eligible_reason(signal=signal)
    if guard is not None:
        return _non_eligible(reason=guard, signal=signal)
    if not signal.turn_started and not signal.has_provider_evidence:
        return _non_eligible(reason="pre_turn_without_provider_evidence", signal=signal)
    identity = candidate.identity
    if identity is None:
        return _non_eligible(reason="identity_absent", signal=signal)
    return _matched_verdict(
        signal=signal,
        identity=identity,
        signatures=effective_signatures(candidate=candidate, builtin=builtin),
    )


def _matched_verdict(
    *,
    signal: AcpFailureSignal,
    identity: AcpCandidateIdentity,
    signatures: tuple[AcpAvailabilitySignature, ...],
) -> AcpAvailabilityFailure | AcpNonEligibleFailure:
    """Apply precedence, then the ambiguity rule, to whatever matched."""
    status = generic_status_reason(signal=signal)
    matched = tuple(
        signature
        for signature in signatures
        if signature_matches(signature=signature, signal=signal)
        and (status is None or signature_discriminates(signature=signature))
    )
    codes = tuple(signature for signature in matched if signature.source == MACHINE_CODE_SOURCE)
    selected = codes or matched
    if not selected:
        return _non_eligible(reason=status or "unmatched", signal=signal)
    verdicts = {_failure(signature=signature, identity=identity) for signature in selected}
    if len(verdicts) > 1:
        return _non_eligible(reason="ambiguous", signal=signal)
    return next(iter(verdicts))


def _failure(
    *, signature: AcpAvailabilitySignature, identity: AcpCandidateIdentity
) -> AcpAvailabilityFailure:
    """The typed verdict one matching signature produces for this candidate.

    Domain scope keys on the signature's `hold_key` override when it
    declares one and on the candidate's own `availability_key` otherwise;
    candidate scope has no override -- the grammar refuses one -- and keys
    on the exact entitlement pair.
    """
    domain = signature.scope == DOMAIN_SCOPE
    return AcpAvailabilityFailure(
        cause=signature.cause,
        scope=signature.scope,
        hold_key=(signature.hold_key or identity.availability_key)
        if domain
        else identity.availability_key,
        availability_key=identity.availability_key,
        candidate_key=None if domain else identity.candidate_key,
        source=signature.source,
    )


def _non_eligible(*, reason: str, signal: AcpFailureSignal) -> AcpNonEligibleFailure:
    """A non-eligible verdict preserving the failure's own identity."""
    return AcpNonEligibleFailure(reason=reason, original_identity=signal.original_identity)
