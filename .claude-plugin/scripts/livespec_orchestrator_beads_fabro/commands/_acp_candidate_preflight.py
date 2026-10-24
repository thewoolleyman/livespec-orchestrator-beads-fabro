"""Which of one node's candidates are still SELECTABLE, in configured order.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A domain record skips every candidate covered by its selected hold
key; a candidate record skips only the exact identity pair. ... The Dispatcher
MUST retain configured order after filtering." And, for the probe: "The
admission-time credential probe creates no observed record. For a fallback-
enabled chain, a provider-limit/rate-limit probe refusal is an ephemeral
candidate-local skip for that one admission evaluation."

FIVE FILTERS, AND THE ORDER BETWEEN THEM IS LOAD-BEARING -- IT *IS* THE
PRECEDENCE RULE. "Typed candidate evidence takes precedence over legacy
cause-text attribution when a chain executed", and consulting typed records
FIRST is what implements that: a candidate carrying typed evidence is skipped
and attributed to its typed cause, and never reaches the legacy blanket to be
re-attributed to a vendor string. Expressing the precedence as ordering rather
than as a second guard also keeps it honest in the one direction that matters
-- a typed record can only exist because the chain executed, so there is no
state in which the guard and the ordering could disagree.

THE UNAVAILABLE-EVIDENCE FILTER IS THIRD, BETWEEN THE RECORDS THAT WERE READ AND
THE TWO THAT COST A ROUND TRIP, and both boundaries are deliberate. "It MAY
continue with candidates whose availability evidence is independently complete;
it MUST NOT treat an unobserved candidate as confirmed unheld." It sits BELOW
the two durable-record filters because a record that WAS read says more than one
that could not be -- reporting the unread source over a live hold would discard
the one fact carrying a bounded expiry and an operator-clearable identity. It
sits ABOVE the probe and the headroom reading because a candidate whose
availability is unknown must not spend a provider request to learn something
else about it; a skip taken here is one neither external filter is asked for.

It is SCOPED TO THE ENTITLEMENTS THE UNREAD SOURCE COULD HAVE HELD, never
applied to the whole chain, and that scoping is the whole of the clause's "MAY
continue". A filter that emptied every chain whenever any source was unreadable
would wedge every dispatch in the fleet the moment one factory became
unreachable, which is not a conservative reading of the clause but a different
rule.

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

THE VALUES THIS DECISION IS MADE OF LIVE IN `_acp_preflight_skips`, split out
by cohesion: what a skip IS, the three disjoint field sets the three kinds
populate, the factory for each, and the two carriers one node's filtering reads
and returns. The reason a headroom skip is carried apart from both other kinds
is recorded there, where the fields are. This module keeps the DECISION -- which
filter a candidate fails, and in what order -- and re-exports those values, so
every caller's import is unchanged.

A SIXTH FILTER NOW SITS INSIDE THE OUTSTANDING-CONFIRMATION ONE, and it is the
only filter that can make a candidate MORE selectable rather than less. "A
candidate covered by an expired domain or candidate hold carries an outstanding
availability confirmation", and `_confirmation_turn` is the seam that runs the
turn which satisfies it (`_acp_availability_probe_run`). It is ABSENT by
default, which keeps every snapshot composer reaching no factory and leaves the
skip standing exactly as it did before the seam existed -- the clause's "MUST
NOT treat an unobserved candidate as confirmed unheld", satisfied by doing
nothing.

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

from livespec_orchestrator_beads_fabro.commands._acp_availability_confirmation import (
    outstanding_confirmation_holds,
)
from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_outcome import (
    probe_confirms,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_coverage import (
    candidate_domain_keys,
    hold_covers_candidate,
    legacy_record_covers_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_skips import (
    HEADROOM_SKIP,
    LEGACY_HOLD_SKIP,
    OUTSTANDING_CONFIRMATION_SKIP,
    PROBE_SKIP,
    PROVIDER_LIMIT_CONDITIONS,
    TYPED_HOLD_SKIP,
    UNAVAILABLE_EVIDENCE_SKIP,
    HeadroomShortfall,
    NodePreflight,
    PreflightInputs,
    SkippedCandidate,
    confirmation_skip,
    ephemeral_skip,
    record_skip,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
    headroom_covers_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    FLOOR_SKIP_KIND,
    PROJECTION_SKIP_KIND,
    SEVEN_DAY_SKIP_KIND,
    headroom_skip_kind,
)

__all__: list[str] = [
    "FLOOR_SKIP_KIND",
    "HEADROOM_SKIP",
    "LEGACY_HOLD_SKIP",
    "OUTSTANDING_CONFIRMATION_SKIP",
    "PROBE_SKIP",
    "PROJECTION_SKIP_KIND",
    "PROVIDER_LIMIT_CONDITIONS",
    "SEVEN_DAY_SKIP_KIND",
    "TYPED_HOLD_SKIP",
    "UNAVAILABLE_EVIDENCE_SKIP",
    "NodePreflight",
    "PreflightInputs",
    "SkippedCandidate",
    "filter_node_candidates",
]


def filter_node_candidates(
    *,
    chain: ResolvedAcpChain,
    inputs: PreflightInputs,
    assessed: dict[str, str],
    confirmed: dict[str, str] | None = None,
) -> NodePreflight:
    """Filter this node's chain, retaining configured order.

    `assessed` is the per-EVALUATION credential memo, shared across every node
    of one verdict and mutated in place. It is a caller-owned dictionary rather
    than module state on purpose: two concurrent evaluations must not share one
    another's probe answers, and a memo that outlived an evaluation would make
    an ephemeral skip durable by the back door.

    `confirmed` is the same memo for the CONFIRMATION TURN, and it matters more
    than the credential one does: a confirmation turn is a real factory run
    spending a real allowance, so a candidate repeated across several nodes --
    which the contract explicitly permits, "MAY be repeated across nodes when
    that identity is truly shared" -- must be probed ONCE per evaluation and not
    once per node. It defaults to ABSENT, which gives this call its own
    per-node memo, so a caller filtering one node in isolation needs no
    bookkeeping it has nowhere to keep.
    """
    ordered = (chain.primary, *chain.fallbacks)
    selectable: list[AcpCandidate] = []
    skipped: list[SkippedCandidate] = []
    assessments: list[SessionHeadroomReading] = []
    turns: dict[str, str] = {} if confirmed is None else confirmed
    for candidate in ordered:
        skip = _skip_for(
            candidate=candidate,
            inputs=inputs,
            assessed=assessed,
            assessments=assessments,
            confirmed=turns,
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
    confirmed: dict[str, str],
) -> SkippedCandidate | None:
    """The first filter this candidate fails, or `None` when it survives all five."""
    for hold in inputs.holds:
        if hold_covers_candidate(hold=hold, candidate=candidate):
            return record_skip(
                candidate=candidate,
                reason=TYPED_HOLD_SKIP,
                cause=hold.cause,
                scope=hold.scope,
                hold_key=hold.hold_key,
            )
    outstanding = outstanding_confirmation_holds(
        expired_holds=inputs.expired_holds,
        confirmations=inputs.confirmations,
        candidate=candidate,
    )
    if outstanding:
        ending = _confirmation_turn(candidate=candidate, inputs=inputs, confirmed=confirmed)
        if ending is None or not probe_confirms(ending=ending):
            return confirmation_skip(candidate=candidate, holds=outstanding, condition=ending)
    legacy = _legacy_provider(candidate=candidate, inputs=inputs)
    if legacy is not None:
        return record_skip(candidate=candidate, reason=LEGACY_HOLD_SKIP, hold_key=legacy)
    if _evidence_unconfirmed(candidate=candidate, inputs=inputs):
        return ephemeral_skip(candidate=candidate, reason=UNAVAILABLE_EVIDENCE_SKIP)
    probed = _probe_skip(candidate=candidate, probe=inputs.probe, assessed=assessed)
    if probed is not None:
        return probed
    return _headroom_skip(candidate=candidate, inputs=inputs, assessments=assessments)


def _confirmation_turn(
    *, candidate: AcpCandidate, inputs: PreflightInputs, confirmed: dict[str, str]
) -> str | None:
    """The ending one confirmation turn reached for this candidate, or `None`.

    `None` means NO turn was run: either no seam was supplied, or the candidate
    carries no identity to key a memo on -- and an identity-less candidate never
    reaches here anyway, since `outstanding_confirmation_holds` leaves it owing
    no confirmation at all.

    MEMOISED PER EVALUATION, on the entitlement PAIR rather than on the
    availability key alone. One allowance can carry several candidates -- a
    different model on the same account -- and the clause confirms "the
    candidate's pinned adapter version, requested model and effort", so a turn
    through one of them says nothing about its sibling. Keying on the account
    would have the first candidate's turn answer for every later one and
    confirm a model nobody ran.
    """
    identity = candidate.identity
    if inputs.confirm is None or identity is None:
        return None
    key = f"{identity.availability_key}\x00{identity.candidate_key}"
    if key not in confirmed:
        confirmed[key] = inputs.confirm(candidate)
    return confirmed[key]


def _legacy_provider(*, candidate: AcpCandidate, inputs: PreflightInputs) -> str | None:
    """The live legacy provider record covering this candidate, if one still does."""
    identity = candidate.identity
    builtin = identity is not None and identity.pair in inputs.builtin_pairs
    for provider in sorted(inputs.legacy_providers):
        if legacy_record_covers_candidate(provider=provider, candidate=candidate, builtin=builtin):
            return provider
    return None


def _evidence_unconfirmed(*, candidate: AcpCandidate, inputs: PreflightInputs) -> bool:
    """Whether an unread source leaves this candidate's availability unknown.

    The test is over the candidate's WHOLE domain set -- its `availability_key`
    plus every override its domain signatures declare -- through the same
    `candidate_domain_keys` a domain hold is matched by. A test against the
    availability key alone would report a candidate routing through an
    unobserved shared pool as confirmed unheld, which is the one thing the
    clause forbids outright.

    An IDENTITY-LESS candidate belongs to no typed domain, so the set is empty
    and no unread typed source can be about it. That keeps the conservative
    legacy posture intact: such an adapter is covered by every live legacy
    record and by no typed one, and skipping it here would strand the one
    adapter shape the contract allows to carry no identity.
    """
    return bool(candidate_domain_keys(candidate=candidate) & inputs.unconfirmed_keys)


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
    return ephemeral_skip(candidate=candidate, reason=PROBE_SKIP, condition=condition)


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

    TWO SHORTFALLS, ONE SKIP, and that is the clause in as many words: "A
    projection skip has exactly the semantics of a floor skip". So the LEVEL
    and the PROJECTION are tested in one condition producing one
    `SkippedCandidate`, rather than as two arms with two skip reasons -- every
    surface downstream (the governing-condition precedence, the availability
    wait, the idle-factory projection) keys on that one reason, and a second
    token would leave a projection-emptied chain unnamed by all three. WHICH of
    the two decided it is recoverable from the reading the skip carries, whose
    projection result says whether a projection skip applied -- so the record
    surfaces can name a projection skip as a projection skip without a second
    skip reason that every consumer would have to learn.
    """
    policy = inputs.headroom
    if policy is None or not headroom_covers_candidate(
        candidate=candidate, builtin_pairs=inputs.builtin_pairs
    ):
        return None
    reading = policy.read()
    if reading not in assessments:
        assessments.append(reading)
    kind = headroom_skip_kind(reading=reading, floor_percent=policy.floor_percent)
    if kind is None:
        return None
    return ephemeral_skip(
        candidate=candidate,
        reason=HEADROOM_SKIP,
        shortfall=HeadroomShortfall(
            reading=reading,
            floor_percent=policy.floor_percent,
            horizon_minutes=policy.horizon_minutes,
            kind=kind,
        ),
    )
