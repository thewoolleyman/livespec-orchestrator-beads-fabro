"""The VALUES one preflight evaluation is made of, and how a skip is recorded.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A domain record skips every candidate covered by its selected hold
key; a candidate record skips only the exact identity pair." This module owns
what a SKIP IS -- its stable machine reason, the three disjoint field sets the
three kinds of skip populate, and the factory for each -- plus the two carriers
one node's filtering reads and returns. `_acp_candidate_preflight` beside it
owns the DECISION: which filter a candidate fails, and in what order.

SPLIT BY COHESION FROM THAT DECISION, and the direction of the one edge between
them is what keeps the pair acyclic: the filter imports these values, and
nothing here knows a filter exists. Every name that crosses the boundary is
PUBLIC, because a cross-module private import is rejected by pyright strict and
by the `private_calls` check alike -- so the four skip factories and the
headroom-shortfall carrier are real interfaces rather than borrowed privates.

THE THREE KINDS OF SKIP KEEP DISJOINT FIELDS, which is the whole reason there
are three factories and not one taking every field. A durable record's TYPED
cause, an ephemeral probe or confirmation CONDITION, and a headroom READING are
three different things, and one factory accepting all of them is how a durable
cause comes to be written onto an ephemeral skip -- after which a credential
merely rate-limited on this host is indistinguishable, downstream, from an
entitlement the provider revoked.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_availability_confirmation import (
    AcpAvailabilityConfirmation,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomPolicy,
    SessionHeadroomReading,
)

__all__: list[str] = [
    "HEADROOM_SKIP",
    "LEGACY_HOLD_SKIP",
    "OUTSTANDING_CONFIRMATION_SKIP",
    "PROBE_SKIP",
    "PROVIDER_LIMIT_CONDITIONS",
    "TYPED_HOLD_SKIP",
    "UNAVAILABLE_EVIDENCE_SKIP",
    "HeadroomShortfall",
    "NodePreflight",
    "PreflightInputs",
    "SkippedCandidate",
    "confirmation_skip",
    "ephemeral_skip",
    "record_skip",
    "skip_identity",
]

# The five reasons a candidate leaves the selectable set, as stable machine
# tokens so a verdict's explanation is greppable rather than prose-matched.
TYPED_HOLD_SKIP = "typed-availability-hold"
OUTSTANDING_CONFIRMATION_SKIP = "outstanding-availability-confirmation"
LEGACY_HOLD_SKIP = "legacy-provider-hold"
PROBE_SKIP = "credential-probe-refusal"
HEADROOM_SKIP = "session-headroom-shortfall"

# The ONE token that is also a governing condition the contract spells, which
# is why it is defined here rather than beside the wait that reports it: "it
# MUST name the outstanding confirmation, unavailable evidence source,
# admission-time credential-probe skip, or admission session-headroom skip".
# `_acp_availability_wait` imports it as `UNAVAILABLE_EVIDENCE`, so the skip a
# filter records and the condition a refusal names cannot drift apart into two
# spellings of one fact.
UNAVAILABLE_EVIDENCE_SKIP = "unavailable-availability-evidence"

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

    `headroom_horizon_minutes` and `headroom_skip_kind` complete that triple
    for the PROJECTED half. The horizon is the second governing dial and is no
    more interpretable apart from the reading than the floor is -- a reader
    seeing an exhaustion two hours out cannot say whether it was refused
    without knowing what horizon was in force. The kind is recorded at the
    moment the skip is decided rather than re-derived later from the reading,
    because the two shortfalls are not exclusive: a reading can sit below the
    floor AND project an exhaustion inside the horizon, and only the filter
    knows which test actually stopped the candidate.
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
    headroom_horizon_minutes: int | None = None
    headroom_skip_kind: str | None = None
    confirmation_observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class HeadroomShortfall:
    """The four facts ONE headroom skip is recorded from, as one value.

    Grouped rather than passed as four parameters because they are one
    measurement and its two governing dials: a caller holding three of them is
    holding an incomplete account, and the ephemeral-skip factory serves the
    probe refusal too, which carries none of them.
    """

    reading: SessionHeadroomReading
    floor_percent: int
    horizon_minutes: int
    kind: str


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
    expired_holds: tuple[AcpAvailabilityHold, ...] = ()
    confirmations: tuple[AcpAvailabilityConfirmation, ...] = ()
    legacy_providers: frozenset[str] = frozenset()
    builtin_pairs: frozenset[tuple[str, str]] = frozenset()
    probe: Callable[[str], str] | None = None
    # The CONFIRMATION-TURN seam: given one candidate owing a post-expiry
    # confirmation, the ending its turn reached. ABSENT means no turn may be
    # run at all, which is the posture every snapshot composer keeps -- wait
    # attention and idle-factory resolve a verdict with no factory call, and
    # the clause's "an unobserved candidate MUST NOT be treated as confirmed
    # unheld" is then satisfied by the skip standing exactly as it did before
    # this seam existed.
    #
    # IT RETURNS AN ENDING RATHER THAN A BOOLEAN, which is the same shape
    # `probe` above takes and for the same reason: the skip has to record WHAT
    # the turn did, because a terminated probe and a measured refusal take
    # different routes and a boolean cannot tell a reader which happened.
    confirm: Callable[[AcpCandidate], str] | None = None
    headroom: SessionHeadroomPolicy | None = None
    # The domain hold keys an UNREAD evidence source leaves unconfirmed. It is
    # a key set rather than the unobservable entries themselves because the
    # question asked of it is a coverage test, and because an entry's shape
    # belongs to the read that produced it: a filter interpreting one would be
    # the second reader of a record this module never sees.
    unconfirmed_keys: frozenset[str] = frozenset()


def record_skip(
    *,
    candidate: AcpCandidate,
    reason: str,
    cause: str | None = None,
    scope: str | None = None,
    hold_key: str | None = None,
) -> SkippedCandidate:
    """A skip a DURABLE record decided, carrying its typed availability cause."""
    availability_key, candidate_key = skip_identity(candidate=candidate)
    return SkippedCandidate(
        availability_key=availability_key,
        candidate_key=candidate_key,
        reason=reason,
        cause=cause,
        scope=scope,
        hold_key=hold_key,
    )


def confirmation_skip(
    *,
    candidate: AcpCandidate,
    holds: tuple[AcpAvailabilityHold, ...],
    condition: str | None = None,
) -> SkippedCandidate:
    """Record the exact expired observations a candidate must re-confirm.

    `condition` is the ENDING a confirmation turn actually reached, when one was
    run, and it rides the ephemeral `condition` field for the reason that field
    exists at all: a probe ending is a local, this-evaluation-only observation
    about one turn, not one of the eight typed availability causes an observed
    outage carries. Writing it into `cause` would make a turn this Dispatcher
    terminated indistinguishable, downstream, from a measured provider ceiling.

    It is `None` when NO turn was run -- which is the pre-probe posture, and the
    one every snapshot composer keeps -- and that absence is deliberately
    distinct from a turn whose ending happened not to confirm: the first says
    nobody asked, and only the second says the candidate was measured.
    """
    availability_key, candidate_key = skip_identity(candidate=candidate)
    return SkippedCandidate(
        availability_key=availability_key,
        candidate_key=candidate_key,
        reason=OUTSTANDING_CONFIRMATION_SKIP,
        condition=condition,
        confirmation_observation_ids=tuple(hold.observation_id for hold in holds),
    )


def ephemeral_skip(
    *,
    candidate: AcpCandidate,
    reason: str,
    condition: str | None = None,
    shortfall: HeadroomShortfall | None = None,
) -> SkippedCandidate:
    """A skip THIS EVALUATION decided, carrying no typed availability cause.

    Kept apart from `record_skip` rather than folded into one factory with
    every field: the two populate disjoint field sets, and one factory taking
    all of them is how a durable cause comes to be written onto an ephemeral
    skip -- which is exactly the conflation both separations above exist to
    prevent.
    """
    availability_key, candidate_key = skip_identity(candidate=candidate)
    return SkippedCandidate(
        availability_key=availability_key,
        candidate_key=candidate_key,
        reason=reason,
        condition=condition,
        headroom=None if shortfall is None else shortfall.reading,
        headroom_floor_percent=None if shortfall is None else shortfall.floor_percent,
        headroom_horizon_minutes=None if shortfall is None else shortfall.horizon_minutes,
        headroom_skip_kind=None if shortfall is None else shortfall.kind,
    )


def skip_identity(*, candidate: AcpCandidate) -> tuple[str | None, str | None]:
    """The candidate's `(availability_key, candidate_key)`, or both `None`."""
    identity = candidate.identity
    if identity is None:
        return (None, None)
    return (identity.availability_key, identity.candidate_key)
