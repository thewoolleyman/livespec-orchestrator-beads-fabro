"""WHICH candidates a live record covers -- typed records and legacy alike.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A domain record skips every candidate covered by its selected
hold key; a candidate record skips only the exact identity pair. Legacy
provider-only records remain readable, clearable by the legacy valve, and
effective until retirement against built-in candidates whose
compatibility alias names that provider plus identity-less legacy
candidates, which every live legacy record covers. Explicitly identified
candidates MUST NOT be broadened to unrelated identities. Typed candidate
evidence takes precedence over legacy cause-text attribution when a chain
executed."

THE DOMAIN SET IS TWO THINGS, NOT ONE, and missing the second half is the
easy way to write this wrong: "A candidate belongs to its
`availability_key` domain plus every override `hold_key` declared by its
domain signatures." A candidate that routes through a shared pool
declares that pool as a `hold_key` override, and a hold on the pool must
skip it even though its own `availability_key` names something else.
Only DOMAIN-scoped signatures contribute -- the grammar refuses a
`hold_key` at candidate scope, so a candidate-scoped signature has none
to contribute.

THE LEGACY BLANKET IS DELIBERATELY WIDE AND DELIBERATELY BOUNDED. It
covers an identity-less legacy adapter unconditionally, because v107's
conservative posture is the whole reason that adapter is allowed to
carry no identity. It covers a BUILT-IN candidate whose availability key
is the provider's own alias, because those aliases exist precisely so an
unexpired legacy record keeps working through the transition. It covers
NOTHING ELSE: a repository that chose `availability_key: "codex"` for an
adapter this build never rendered is an explicitly identified candidate,
and broadening a legacy vendor record onto it is the "unrelated
identities" case the contract forbids. That is why `builtin` is the
caller's fact -- read from the rendered-bytes table -- and never inferred
from how a key is spelled.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    CANDIDATE_SCOPE,
    DOMAIN_SCOPE,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold

__all__: list[str] = [
    "candidate_domain_keys",
    "hold_covers_candidate",
    "legacy_record_covers_candidate",
    "legacy_yields_to_typed",
]


def candidate_domain_keys(*, candidate: AcpCandidate) -> frozenset[str]:
    """Every domain hold key this candidate belongs to.

    The empty set for an identity-less candidate: it belongs to no typed
    domain at all, which is what keeps a typed domain hold from reaching
    the conservative legacy path.
    """
    identity = candidate.identity
    if identity is None:
        return frozenset()
    overrides = {
        signature.hold_key
        for signature in candidate.signatures
        if signature.scope == DOMAIN_SCOPE and signature.hold_key is not None
    }
    return frozenset({identity.availability_key, *overrides})


def hold_covers_candidate(*, hold: AcpAvailabilityHold, candidate: AcpCandidate) -> bool:
    """Whether one live typed record skips this candidate.

    Candidate scope is an EXACT pair test and domain scope a membership
    test, and neither ever falls back to the other: a candidate record
    naming an identity this candidate does not hold covers nothing, even
    when both sit in the same domain.
    """
    identity = candidate.identity
    if identity is None:
        return False
    if hold.scope == CANDIDATE_SCOPE:
        return (hold.hold_key, hold.candidate_key) == identity.pair
    return hold.hold_key in candidate_domain_keys(candidate=candidate)


def legacy_record_covers_candidate(
    *, provider: str, candidate: AcpCandidate, builtin: bool
) -> bool:
    """Whether an unexpired LEGACY provider record still covers this candidate.

    `builtin` says this candidate's resolved adapter is one THIS BUILD
    rendered, so its `availability_key` is the provenance-assigned
    compatibility alias rather than an operator's chosen string. See the
    module docstring for why that distinction is the whole boundary.
    """
    identity = candidate.identity
    if identity is None:
        return True
    return builtin and identity.availability_key == provider


def legacy_yields_to_typed(
    *, chain_executed: bool, candidate: AcpCandidate, holds: tuple[AcpAvailabilityHold, ...]
) -> bool:
    """Whether typed candidate evidence supersedes legacy attribution here.

    "Typed candidate evidence takes precedence over legacy cause-text
    attribution when a chain executed." Both conditions are load-bearing
    and neither implies the other. A chain that did NOT execute produced
    no typed evidence to prefer, so the legacy blanket still governs; and
    typed DOMAIN evidence is not the same claim as candidate evidence --
    it says the entitlement is spent, not that this identity was tried --
    so only a candidate-scoped record covering this exact candidate
    displaces the legacy attribution of it.
    """
    return chain_executed and any(
        hold.scope == CANDIDATE_SCOPE and hold_covers_candidate(hold=hold, candidate=candidate)
        for hold in holds
    )
