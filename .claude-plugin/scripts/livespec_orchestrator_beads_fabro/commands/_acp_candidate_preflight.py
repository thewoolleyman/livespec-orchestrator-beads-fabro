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

The two EXTERNAL filters run last because each costs a round trip and each
one's answer is thrown away at the end of the evaluation. A candidate already
skipped by a durable record is never probed and never assessed for headroom,
which is most of why "at most once per admission evaluation" is cheap to
honour.

THE SESSION-HEADROOM FILTER IS FOURTH, AND BELOW THE PROBE SPECIFICALLY.
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "With a positive floor, a successful credential-
usability probe MUST NOT override a headroom skip." A probe answers "can this
credential call the provider at all" and reports USABLE right up to the
session limit -- measured on hp 2026-10-14, where a run was refused
mid-implement on the session limit while `claude-cred-status` returned
`usable` two minutes later. So the probe cannot stand in for the reading, and
putting the reading above the probe would make a provider-limited credential
report a headroom shortfall instead of the limit it actually hit.

THE TWO EPHEMERAL SKIPS ARE EPHEMERAL IN EVERY SENSE THE CONTRACT NAMES. Neither
writes a journal record, mints a hold or refreshes an expiry, and the probe skip
is keyed on the ONE candidate's own availability key rather than broadened to its
provider. Nothing in this module can persist anything: it is handed values and
returns values, which is what lets admission, rework admission, wait attention
and idle-factory consume one verdict without four of them disagreeing about what
a probe or a reading said. For headroom that is the clause's own requirement --
"A reading creates NO observed availability record and retires none" -- and the
reason it holds here is structural rather than careful: this module is handed no
journal to write to.

A HEADROOM SKIP IS CARRIED SEPARATELY FROM BOTH OTHER KINDS, in `headroom` and
`headroom_floor_percent`, because the clause forbids representing it as an
observed hold and because a reading is only interpretable beside the floor it
was graded against. The READING RIDES ALONG rather than being re-taken by a
consumer: the refusal and the selection record must both name the same
measurement, and a second read would be a second measurement.

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
    SessionHeadroomPolicy,
    SessionHeadroomReading,
    headroom_covers_candidate,
    headroom_skips_candidate,
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
HEADROOM_SKIP = "session-headroom-shortfall"

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

    `headroom` and `headroom_floor_percent` are the THIRD such separation, for
    the same reason one level on: a session-headroom shortfall is a measurement
    of a usage window, not a provider refusal of any kind, and the clause
    forbids representing it as an observed hold. The floor travels with the
    reading because neither is interpretable without the other.
    """

    availability_key: str | None
    candidate_key: str | None
    reason: str
    cause: str | None = None
    scope: str | None = None
    hold_key: str | None = None
    condition: str | None = None
    headroom: SessionHeadroomReading | None = None
    headroom_floor_percent: int | None = None


@dataclass(frozen=True, kw_only=True)
class NodePreflight:
    """One node's surviving candidates in configured order, and what left.

    `assessments` is every DISTINCT session-headroom reading this node's filter
    took, skipped or not. The clause requires the reading to be journaled for
    each affected work-item whether or not it refused anything, so a reading
    reported only through `skipped` would vanish on exactly the admitted case
    the journal exists to record.
    """

    node: str
    enabled: bool
    candidates: tuple[AcpCandidate, ...]
    skipped: tuple[SkippedCandidate, ...]
    assessments: tuple[SessionHeadroomReading, ...] = ()

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
    headroom: SessionHeadroomPolicy | None = None


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
    assessments: list[SessionHeadroomReading] = []
    for candidate in ordered:
        skip = _skip_for(
            candidate=candidate, inputs=inputs, assessed=assessed, assessments=assessments
        )
        if skip is None:
            selectable.append(candidate)
        else:
            skipped.append(skip)
    return NodePreflight(
        node=chain.node,
        enabled=chain.enabled,
        candidates=tuple(selectable),
        skipped=tuple(skipped),
        assessments=tuple(assessments),
    )


def _skip_for(
    *,
    candidate: AcpCandidate,
    inputs: PreflightInputs,
    assessed: dict[str, str],
    assessments: list[SessionHeadroomReading],
) -> SkippedCandidate | None:
    """The first filter this candidate fails, or `None` when it survives all four."""
    for hold in inputs.holds:
        if hold_covers_candidate(hold=hold, candidate=candidate):
            return _record_skip(
                candidate=candidate,
                reason=TYPED_HOLD_SKIP,
                cause=hold.cause,
                scope=hold.scope,
                hold_key=hold.hold_key,
            )
    legacy = _legacy_provider(candidate=candidate, inputs=inputs)
    if legacy is not None:
        return _record_skip(candidate=candidate, reason=LEGACY_HOLD_SKIP, hold_key=legacy)
    probed = _probe_skip(candidate=candidate, probe=inputs.probe, assessed=assessed)
    if probed is not None:
        return probed
    return _headroom_skip(candidate=candidate, inputs=inputs, assessments=assessments)


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
    return _ephemeral_skip(candidate=candidate, reason=PROBE_SKIP, condition=condition)


def _headroom_skip(
    *,
    candidate: AcpCandidate,
    inputs: PreflightInputs,
    assessments: list[SessionHeadroomReading],
) -> SkippedCandidate | None:
    """Assess a COVERED candidate's projected credential, and skip only a shortfall.

    The reading is recorded in `assessments` BEFORE the skip is decided, which
    is what makes an above-floor reading journalable: the clause requires every
    assessment to be journaled for each affected work-item, not only the ones
    that refused something.
    """
    policy = inputs.headroom
    if policy is None or not headroom_covers_candidate(
        candidate=candidate, builtin_pairs=inputs.builtin_pairs
    ):
        return None
    reading = policy.read()
    if reading not in assessments:
        assessments.append(reading)
    if not headroom_skips_candidate(reading=reading, floor_percent=policy.floor_percent):
        return None
    return _ephemeral_skip(
        candidate=candidate,
        reason=HEADROOM_SKIP,
        headroom=reading,
        headroom_floor_percent=policy.floor_percent,
    )


def _record_skip(
    *,
    candidate: AcpCandidate,
    reason: str,
    cause: str | None = None,
    scope: str | None = None,
    hold_key: str | None = None,
) -> SkippedCandidate:
    """A skip a DURABLE record decided, carrying its typed availability cause."""
    availability_key, candidate_key = _skip_identity(candidate=candidate)
    return SkippedCandidate(
        availability_key=availability_key,
        candidate_key=candidate_key,
        reason=reason,
        cause=cause,
        scope=scope,
        hold_key=hold_key,
    )


def _ephemeral_skip(
    *,
    candidate: AcpCandidate,
    reason: str,
    condition: str | None = None,
    headroom: SessionHeadroomReading | None = None,
    headroom_floor_percent: int | None = None,
) -> SkippedCandidate:
    """A skip THIS EVALUATION decided, carrying no typed availability cause.

    Kept apart from `_record_skip` rather than folded into one factory with
    every field: the two populate disjoint field sets, and one factory taking
    all of them is how a durable cause comes to be written onto an ephemeral
    skip -- which is exactly the conflation both separations above exist to
    prevent.
    """
    availability_key, candidate_key = _skip_identity(candidate=candidate)
    return SkippedCandidate(
        availability_key=availability_key,
        candidate_key=candidate_key,
        reason=reason,
        condition=condition,
        headroom=headroom,
        headroom_floor_percent=headroom_floor_percent,
    )


def _skip_identity(*, candidate: AcpCandidate) -> tuple[str | None, str | None]:
    """The candidate's `(availability_key, candidate_key)`, or both `None`."""
    identity = candidate.identity
    if identity is None:
        return (None, None)
    return (identity.availability_key, identity.candidate_key)
