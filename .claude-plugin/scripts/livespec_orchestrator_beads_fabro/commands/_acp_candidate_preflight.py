"""Which of one node's candidates are still SELECTABLE, in configured order.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A domain record skips every candidate covered by its selected hold
key; a candidate record skips only the exact identity pair. ... The Dispatcher
MUST retain configured order after filtering." And, for the probe: "The
admission-time credential probe creates no observed record. For a fallback-
enabled chain, a provider-limit/rate-limit probe refusal is an ephemeral
candidate-local skip for that one admission evaluation."

FOUR FILTERS, AND THE ORDER BETWEEN THEM IS LOAD-BEARING -- IT *IS* THE
PRECEDENCE RULE. "Typed candidate evidence takes precedence over legacy
cause-text attribution when a chain executed", and consulting typed records
FIRST is what implements that: a candidate carrying typed evidence is skipped
and attributed to its typed cause, and never reaches the legacy blanket to be
re-attributed to a vendor string. Expressing the precedence as ordering rather
than as a second guard also keeps it honest in the one direction that matters
-- a typed record can only exist because the chain executed, so there is no
state in which the guard and the ordering could disagree.

The SESSION-HEADROOM filter sits third, and it costs nothing to place there:
its reading arrives as a VALUE on `PreflightInputs`, already taken once for the
whole evaluation, so there is no call to defer. The credential probe still runs
LAST because it is the only filter that costs an external call per candidate
and the only one whose answer is thrown away at the end of the evaluation. A
candidate already skipped by a durable record or by the headroom reading is
never probed, which is most of why "at most once per admission evaluation" is
cheap to honour -- and it is also why "a successful credential-usability probe
MUST NOT override a headroom skip" needs no guard of its own: the probe is
never consulted for a candidate headroom already removed.

THE PROBE SKIP IS EPHEMERAL IN EVERY SENSE THE CONTRACT NAMES. It writes no
journal record, mints no hold, refreshes no expiry, and is keyed on the ONE
candidate's own availability key rather than broadened to its provider. Nothing
in this module can persist anything: it is handed values and returns values,
which is what lets admission, rework admission, wait attention and idle-factory
consume one verdict without four of them disagreeing about what a probe said.

WHY THE CREDENTIAL IS KEYED ON `availability_key`. That key names the account or
router a candidate authenticates against; `candidate_key` names the model or
entitlement WITHIN it. Two candidates that differ only by model therefore share
one credential, and probing per pair would assess the same credential twice and
could return two different answers for one thing. An identity-less legacy
candidate names no credential at all and is never probed -- it retains the v107
containment path, which is the whole reason it is allowed to carry no identity.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_coverage import (
    hold_covers_candidate,
    legacy_record_covers_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomGate,
    candidate_is_covered,
)

__all__: list[str] = [
    "HEADROOM_SKIP",
    "LEGACY_HOLD_SKIP",
    "PROBE_SKIP",
    "PROVIDER_LIMIT_CONDITIONS",
    "TYPED_HOLD_SKIP",
    "NodePreflight",
    "PreflightInputs",
    "SkippedCandidate",
    "filter_node_candidates",
]

# The four reasons a candidate leaves the selectable set, as stable machine
# tokens so a verdict's explanation is greppable rather than prose-matched.
TYPED_HOLD_SKIP = "typed-availability-hold"
LEGACY_HOLD_SKIP = "legacy-provider-hold"
PROBE_SKIP = "credential-probe-refusal"
HEADROOM_SKIP = "session-headroom-skip"

# The ONLY probe conditions that produce an ephemeral skip. Every other refusal
# -- absent, revoked, denied, unassessable -- is a fault no fallback repairs, so
# it is left to the dispatch path's own refusal exactly as before. Widening this
# set would convert a misconfigured wrapper into a silent chain exhaustion.
PROVIDER_LIMIT_CONDITIONS: frozenset[str] = frozenset({"exhausted", "rate_limited"})


@dataclass(frozen=True, kw_only=True)
class SkippedCandidate:
    """One candidate that will not be selected, and the typed reason why.

    `cause`, `scope` and `hold_key` carry the TYPED availability cause when a
    durable record supplied one. They are what a reached empty chain terminates
    with, so they are recorded at the moment the skip is decided rather than
    re-derived later from a ledger that may since have moved.

    `condition` is the SEPARATE field an ephemeral probe refusal reports under,
    and the separation is the point: a probe condition is a local, this-
    evaluation-only observation about a credential, not one of the eight typed
    availability causes an observed provider outage carries. Writing it into
    `cause` would make a credential that is merely rate-limited on this host
    indistinguishable, downstream, from an entitlement the provider revoked.

    A SESSION-HEADROOM skip carries NONE of those fields -- only its `reason`
    token. Its assessment lives on the evaluation's own
    `PreflightInputs.session_headroom` gate rather than on the row, because ONE
    reading governs every covered candidate of that evaluation: copying it onto
    each row would create as many copies as there are skips, and a later edit
    that moved one of them would make the rows disagree about a single
    observation. `_dispatcher_session_headroom_records` reads the gate.
    """

    availability_key: str | None
    candidate_key: str | None
    reason: str
    cause: str | None = None
    scope: str | None = None
    hold_key: str | None = None
    condition: str | None = None


@dataclass(frozen=True, kw_only=True)
class NodePreflight:
    """One node's surviving candidates in configured order, and what left."""

    node: str
    enabled: bool
    candidates: tuple[AcpCandidate, ...]
    skipped: tuple[SkippedCandidate, ...]

    @property
    def exhausted(self) -> bool:
        """Whether no candidate remains for this node."""
        return not self.candidates


@dataclass(frozen=True, kw_only=True)
class PreflightInputs:
    """Everything the filter reads, resolved ONCE at a fixed evaluation time.

    Holding the live records as a value rather than a reader is what makes the
    contract's "at one fixed evaluation time" a property of the type: two nodes
    filtered from one `PreflightInputs` cannot see a ledger that moved between
    them.
    """

    holds: tuple[AcpAvailabilityHold, ...] = ()
    legacy_providers: frozenset[str] = frozenset()
    builtin_pairs: frozenset[tuple[str, str]] = frozenset()
    probe: Callable[[str], str] | None = None
    # The ONE session-headroom reading and floor governing this evaluation, or
    # `None` when no usage request was made -- a repository rendering no covered
    # candidate, or a surface forbidden from issuing one (snapshot composition,
    # wait attention, the idle-factory projection). `None` skips nothing, which
    # is what keeps those surfaces free of any external call.
    session_headroom: SessionHeadroomGate | None = None


def filter_node_candidates(
    *,
    chain: ResolvedAcpChain,
    inputs: PreflightInputs,
    assessed: dict[str, str],
) -> NodePreflight:
    """Filter this node's chain, retaining configured order.

    `assessed` is the per-EVALUATION credential memo, shared across every node
    of one verdict and mutated in place. It is a caller-owned dictionary rather
    than module state on purpose: two concurrent evaluations must not share one
    another's probe answers, and a memo that outlived an evaluation would make
    an ephemeral skip durable by the back door.
    """
    ordered = (chain.primary, *chain.fallbacks)
    selectable: list[AcpCandidate] = []
    skipped: list[SkippedCandidate] = []
    for candidate in ordered:
        skip = _skip_for(candidate=candidate, inputs=inputs, assessed=assessed)
        if skip is None:
            selectable.append(candidate)
        else:
            skipped.append(skip)
    return NodePreflight(
        node=chain.node,
        enabled=chain.enabled,
        candidates=tuple(selectable),
        skipped=tuple(skipped),
    )


def _skip_for(
    *,
    candidate: AcpCandidate,
    inputs: PreflightInputs,
    assessed: dict[str, str],
) -> SkippedCandidate | None:
    """The first filter this candidate fails, or `None` when it survives all four."""
    for hold in inputs.holds:
        if hold_covers_candidate(hold=hold, candidate=candidate):
            return _skipped(
                candidate=candidate,
                reason=TYPED_HOLD_SKIP,
                cause=hold.cause,
                scope=hold.scope,
                hold_key=hold.hold_key,
            )
    legacy = _legacy_provider(candidate=candidate, inputs=inputs)
    if legacy is not None:
        return _skipped(candidate=candidate, reason=LEGACY_HOLD_SKIP, hold_key=legacy)
    headroom = _headroom_skip(candidate=candidate, gate=inputs.session_headroom)
    if headroom is not None:
        return headroom
    return _probe_skip(candidate=candidate, probe=inputs.probe, assessed=assessed)


def _headroom_skip(
    *, candidate: AcpCandidate, gate: SessionHeadroomGate | None
) -> SkippedCandidate | None:
    """Skip a COVERED candidate when this evaluation's reading is below the floor.

    Both guards fail open, in the direction that adds no restriction. No gate
    means no usage request was made, and an uncovered candidate is outside the
    clause -- neither is evidence against the candidate, so neither skips it.
    """
    if gate is None or not gate.skips_covered_candidates:
        return None
    if not candidate_is_covered(candidate=candidate):
        return None
    return _skipped(candidate=candidate, reason=HEADROOM_SKIP)


def _legacy_provider(*, candidate: AcpCandidate, inputs: PreflightInputs) -> str | None:
    """The live legacy provider record covering this candidate, if one still does."""
    identity = candidate.identity
    builtin = identity is not None and identity.pair in inputs.builtin_pairs
    for provider in sorted(inputs.legacy_providers):
        if legacy_record_covers_candidate(provider=provider, candidate=candidate, builtin=builtin):
            return provider
    return None


def _probe_skip(
    *,
    candidate: AcpCandidate,
    probe: Callable[[str], str] | None,
    assessed: dict[str, str],
) -> SkippedCandidate | None:
    """Assess this candidate's credential at most once, and skip only a limit."""
    identity = candidate.identity
    if probe is None or identity is None:
        return None
    key = identity.availability_key
    if key not in assessed:
        assessed[key] = probe(key)
    condition = assessed[key]
    if condition not in PROVIDER_LIMIT_CONDITIONS:
        return None
    return _skipped(candidate=candidate, reason=PROBE_SKIP, condition=condition)


def _skipped(
    *,
    candidate: AcpCandidate,
    reason: str,
    cause: str | None = None,
    scope: str | None = None,
    hold_key: str | None = None,
    condition: str | None = None,
) -> SkippedCandidate:
    identity = candidate.identity
    return SkippedCandidate(
        availability_key=None if identity is None else identity.availability_key,
        candidate_key=None if identity is None else identity.candidate_key,
        reason=reason,
        cause=cause,
        scope=scope,
        hold_key=hold_key,
        condition=condition,
    )
