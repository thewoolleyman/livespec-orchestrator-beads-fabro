"""WHEN the Dispatcher looks again after an admission-required chain emptied.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "If any potentially reachable node has no eligible candidate, the
item MUST remain ready without a claim or blocked reason, and the Dispatcher
MUST schedule another admission evaluation. ... The scheduled evaluation falls
at the earliest expiry among the holds that empty a chain, and otherwise after
`dispatcher.credential_reprobe_interval_seconds`; no human valve is the remedy
for that wait."

PURE, AND HANDED ITS EVIDENCE RATHER THAN READING IT. The verdict and the live
holds both come from ONE ledger read, so passing them in as values is what
makes "at one fixed evaluation time" a property of the call rather than a
convention two readers keep -- the same reason `PreflightInputs` holds records
instead of a reader. It also means the instant is a FUNCTION of the
authoritative availability evidence, which is what lets a restarted Dispatcher
reconstruct the identical wait from the journal with no scheduler state to
persist and nothing to lose.

THE INSTANT AND THE NAMED NODE ANSWER DIFFERENT QUESTIONS, and fusing them is
the mistake this module is shaped to prevent. `reevaluate_at` is a MINIMUM over
every hold that empties any admission-required chain -- the first moment the
situation could change at all -- while `node` is the FIRST emptied node in
graph order, which is what the containment refusal must name. Reading the
instant off the named node's own holds is wrong whenever a later node is held
by a record that retires sooner, and it is wrong invisibly: both values are
well-formed instants.

WHY A TYPED SKIP IS RE-MATCHED AGAINST THE HANDED-IN HOLDS INSTEAD OF TRUSTED.
`SkippedCandidate` records the scope and hold key a durable record decided the
skip under, but not that record's expiry -- and the clause forbids this refusal
an invented one. So the expiry is taken from the hold itself, matched on the
scope and key the skip names, and a typed skip whose record the evidence no
longer carries contributes NO hold and NO expiry. That direction is chosen: the
alternative is a refusal naming a hold identity nothing substantiates, which at
the journal is indistinguishable from an observed outage.

A DOMAIN HOLD IS MATCHED WITHOUT ITS CANDIDATE KEY, and that asymmetry is not
an oversight. `_record_skip` writes the SKIPPED CANDIDATE's own `candidate_key`
while a domain record carries none, so an equality test on the triple would
match no domain hold at all -- and a domain hold is the common case, since that
is what a provider allowance outage mints.

EVERY ARM THAT CANNOT READ A CLOCK FALLS BACK, NEVER FORWARD. An unreadable
hold expiry takes the cadence, and an unreadable evaluation clock schedules
nothing at all. Adopting unreadable text as the instant would write a
`reevaluate_at` no comparison can order, which every later pass reads as
already due -- the busy loop this wait exists to bound.

A CONFIGURATION REFUSAL IS NOT AN AVAILABILITY WAIT. An unsupported graph or an
unresolvable chain table names no admission-required node and no observation,
and no amount of waiting repairs it, so it yields no wait rather than an
instant. Manufacturing one would report a committed configuration fault as a
provider outage that expires on its own.

AN UNAVAILABLE EVIDENCE SOURCE SCHEDULES A WAIT EVEN WHEN NO CHAIN EMPTIED, and
that arm is the one a reader is most likely to delete as redundant. "An
unreadable or incomplete evidence source is unavailable, not an empty hold set.
The Dispatcher MUST surface that condition and retry observation on a bounded
cadence." Keying the whole derivation on `exhausted` satisfied the surfacing and
nothing else: a factory whose listing refuses leaves every candidate's evidence
incomplete without emptying anything, so the condition was reported on the
verdict and then never looked at again. Such a wait names NO node -- there is no
admission-required node lacking a candidate -- which is why `node` is optional
rather than carrying the empty string: a reader joining on a node name must be
able to tell "no node is empty" from a node whose id did not survive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    HEADROOM_SKIP,
    LEGACY_HOLD_SKIP,
    OUTSTANDING_CONFIRMATION_SKIP,
    PROBE_SKIP,
    TYPED_HOLD_SKIP,
    UNAVAILABLE_EVIDENCE_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import DOMAIN_SCOPE
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    AcpAvailabilityHold,
    parse_hold_instant,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

__all__: list[str] = [
    "CONFIRMATION_ENDINGS_FIELD",
    "GOVERNING_CONDITION_PRECEDENCE",
    "UNAVAILABLE_EVIDENCE",
    "AvailabilityWait",
    "GoverningHold",
    "availability_wait",
    "availability_wait_delay_seconds",
    "availability_wait_refusal_fields",
]

# The refusal field naming the ending each confirmation turn reached. Named
# rather than spelled at the one call site, so the writer and every reader
# joining on it cannot drift into two spellings of one key.
CONFIRMATION_ENDINGS_FIELD = "confirmation_turn_endings"

# The condition a refusal names when no skip on the emptied node named one, and
# the condition an unavailable evidence source names when it emptied one itself.
# "When no hold governs the refusal, it MUST name the outstanding
# confirmation, unavailable evidence source, admission-time credential-probe
# skip, or admission session-headroom skip instead." It is ALIASED from the
# filter's own skip reason rather than spelled a second time: the two are one
# fact, and two literals of one fact is how a journal row comes to disagree
# with the skip that produced it.
UNAVAILABLE_EVIDENCE = UNAVAILABLE_EVIDENCE_SKIP

# Which skip governs when several emptied one chain. A DURABLE record outranks
# an ephemeral one because it is the fact carrying a bounded expiry and the one
# an operator can clear; the typed record outranks the legacy blanket for the
# same reason the filter consults it first. The unavailable source sits between
# the records that WERE read and the two local skips, exactly where the filter
# applies it -- a precedence that disagreed with the filter's own ordering
# would name a condition for a candidate the filter never reached.
#
# THE OUTSTANDING CONFIRMATION SITS BELOW BOTH HOLDS AND ABOVE THE THREE LOCAL
# CONDITIONS, which is the clause's own ordering rather than the filter's. "When
# no hold governs the refusal, it MUST name the outstanding confirmation,
# unavailable evidence source, admission-time credential-probe skip, or
# admission session-headroom skip instead" -- so a LIVE record still governs a
# node that also owes a confirmation, even though the filter consults the
# confirmation first. That is the one place the two orderings diverge, and the
# clause decides it: a confirmation names no expiry and nothing an operator can
# clear, while a live hold names both.
#
# Omitting it entirely is the fail-wrong direction, and it is silent: a node
# emptied by a confirmation alone substantiates no condition in the tuple, so
# it fell through to `UNAVAILABLE_EVIDENCE` and reported an unreadable evidence
# source for a chain whose evidence had been read perfectly well -- a remedy
# pointing at a factory nobody needs to look at.
GOVERNING_CONDITION_PRECEDENCE: tuple[str, ...] = (
    TYPED_HOLD_SKIP,
    LEGACY_HOLD_SKIP,
    OUTSTANDING_CONFIRMATION_SKIP,
    UNAVAILABLE_EVIDENCE_SKIP,
    PROBE_SKIP,
    HEADROOM_SKIP,
)

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True, kw_only=True)
class GoverningHold:
    """One live observation that emptied an admission-required chain.

    The contract requires the containment refusal to "name applicable hold
    observations and their expiries when present", so the identity and the
    expiry travel together -- an expiry with no observation names nothing an
    operator could clear, and an observation with no expiry says nothing about
    when the wait ends.
    """

    observation_id: str
    scope: str
    hold_key: str
    candidate_key: str | None
    cause: str
    expires_at: str


@dataclass(frozen=True, kw_only=True)
class AvailabilityWait:
    """The scheduled reevaluation one admission evaluation produced.

    `node` is `None` exactly when NO admission-required chain emptied, which is
    the unavailable-evidence arm described in the module docstring: the
    condition is real and bounded, and there is no node it can be attributed
    to. The empty string would read as a node whose id was lost.

    `legacy_provider` names the vendor whose LEGACY blanket emptied the named
    node, and it is here rather than left to a consumer for the same reason
    `holds` is: a surface offering the legacy clearance valve has to name the
    provider, and re-deriving it from the journal would be a second reading of
    one evaluation that could name a different vendor from the skip the filter
    actually recorded. It is `None` on every other condition — including a
    `legacy-provider-hold` whose skip recorded no key — because a blanket whose
    vendor nothing substantiates is one no valve can be pointed at.

    `confirmation_endings` is the ending each CONFIRMATION TURN reached on the
    named node, and it answers the one question the governing condition cannot:
    whether the Dispatcher ASKED. A node emptied because no probe seam was
    supplied and a node emptied because every probe was TERMINATED both render
    as an outstanding confirmation, and they have different remedies — the
    first waits out the cadence, the second says the turns are being killed. It
    is EMPTY when no turn was run, which is deliberately distinct from a turn
    whose ending happened not to confirm: a filled-in ending would report a
    measurement nobody took.
    """

    node: str | None
    nodes: tuple[str, ...]
    governing_condition: str
    reevaluate_at: str
    holds: tuple[GoverningHold, ...]
    unobservable_observations: int
    legacy_provider: str | None = None
    confirmation_endings: tuple[str, ...] = ()


def availability_wait(
    *,
    verdict: AcpPreflightVerdict,
    holds: tuple[AcpAvailabilityHold, ...],
    now_iso: str,
    reprobe_interval_seconds: int,
) -> AvailabilityWait | None:
    """Schedule the next admission evaluation, or `None` when none is owed.

    `None` means there is nothing to look again for: every admission-required
    chain still holds a candidate AND every evidence source was readable, or the
    verdict is a configuration refusal that waiting cannot repair, or the
    evaluation clock itself could not be read.
    """
    if verdict.refusal is not None or not (verdict.exhausted or verdict.unobservable):
        return None
    now = parse_hold_instant(text=now_iso)
    if now is None:
        return None
    # Ordered by `exhausted` rather than by `verdict.nodes`, because the named
    # node must be the first EMPTIED one in graph order.
    #
    # AN EXHAUSTED NODE WITH NO FILTER RECORD IS TOLERATED, NOT INDEXED. Inside
    # `build_acp_preflight_verdict` every exhausted node does have a
    # `NodePreflight` -- `_exhausted` is computed from them -- but the verdict
    # is a plain value every consumer may construct, and a caller naming an
    # exhausted node without its per-node record is reporting an outage it
    # recorded no skips for. Indexing would raise from inside the pre-claim
    # admission filter, which is the one place a bug-class escape strands a row;
    # and such a node substantiates no condition and no hold, so it falls to
    # `UNAVAILABLE_EVIDENCE` and the cadence rather than to an invented
    # identity.
    by_node = {preflight.node: preflight for preflight in verdict.nodes}
    emptied = tuple(by_node[node] for node in verdict.exhausted if node in by_node)
    governing = _governing_holds(emptied=emptied, holds=holds)
    return AvailabilityWait(
        node=verdict.exhausted[0] if verdict.exhausted else None,
        nodes=verdict.exhausted,
        governing_condition=_governing_condition(emptied=emptied),
        reevaluate_at=_reevaluate_at(
            governing=governing, now=now, reprobe_interval_seconds=reprobe_interval_seconds
        ),
        holds=governing,
        unobservable_observations=len(verdict.unobservable),
        legacy_provider=_legacy_provider(emptied=emptied),
        confirmation_endings=_confirmation_endings(emptied=emptied),
    )


def availability_wait_refusal_fields(*, wait: AvailabilityWait | None) -> dict[str, object]:
    """The containment-refusal fields one scheduled wait contributes.

    EMPTY for `None`, which is what keeps every pre-existing refusal record
    byte-identical: a viable verdict and a configuration refusal add no keys at
    all, exactly as `headroom_refusal_fields` adds none unless headroom emptied
    a chain. That is the additive guarantee, expressed as the absence of a key
    rather than as a null the next reader has to interpret.

    `governing_hold_observations` is a LIST and is empty rather than absent when
    no hold governs, because the clause requires the refusal to name applicable
    observations "when present" -- an empty list says the question was asked and
    the answer was none, while a missing key is what a record from a build
    predating this decision looks like.

    `CONFIRMATION_ENDINGS_FIELD` is a LIST on the same reasoning: empty says no
    confirmation turn was run on the named node, which is a different state
    from a turn that ran and did not confirm, and an absent key would make both
    indistinguishable from a build that never ran turns at all.
    """
    if wait is None:
        return {}
    return {
        "governing_condition": wait.governing_condition,
        CONFIRMATION_ENDINGS_FIELD: list(wait.confirmation_endings),
        "admission_required_node": wait.node,
        "admission_required_nodes_lacking_candidate": list(wait.nodes),
        "scheduled_reevaluation_at": wait.reevaluate_at,
        "governing_hold_observations": [
            {
                "observation_id": hold.observation_id,
                "scope": hold.scope,
                "hold_key": hold.hold_key,
                "candidate_key": hold.candidate_key,
                "cause": hold.cause,
                "expires_at": hold.expires_at,
            }
            for hold in wait.holds
        ],
    }


def availability_wait_delay_seconds(*, wait: AvailabilityWait, now_iso: str) -> int | None:
    """How long is left of this wait, or `None` when there is nothing to sleep for.

    `None` IS NOT ZERO, and conflating them is the defect this function exists
    to prevent. Zero is a SCHEDULED IMMEDIATE RETRY: a loop reading it sleeps
    for no time, reevaluates, finds the chain still empty and reads zero again
    -- the busy loop the bounded cadence exists to replace. `None` says the
    scheduled instant has arrived, so this pass's own reevaluation is the one
    the schedule asked for and the loop's ordinary cadence governs what happens
    next. The clause's "reevaluated once per loop pass" is exactly that
    distinction.

    THE EXACT INSTANT COUNTS AS DUE. A wait whose instant equals now is over,
    not still running, so the comparison is `<=` -- the same direction
    `hold_expired` takes for the record this instant was usually derived from,
    which is what keeps a hold's retirement and its wait's expiry from
    disagreeing by one second.

    An unreadable clock yields `None` rather than a delay, because the only
    values available to compute one from are the ones that did not parse, and
    holding a loop for a duration derived from unparseable text is strictly
    worse than reevaluating once.
    """
    scheduled = parse_hold_instant(text=wait.reevaluate_at)
    now = parse_hold_instant(text=now_iso)
    if scheduled is None or now is None or scheduled <= now:
        return None
    return int((scheduled - now).total_seconds())


def _governing_condition(*, emptied: tuple[NodePreflight, ...]) -> str:
    """What emptied the FIRST emptied chain, by the precedence above.

    Scoped to that one node rather than to every emptied node, because the
    refusal names ONE admission-required node and the condition has to be the
    condition of that node -- a precedence taken across the whole set would
    report a typed hold on a later node as the reason the named one is empty.

    NO emptied record at all, and a record naming no skip, both reach
    `UNAVAILABLE_EVIDENCE` below, which is the honest reading of each: the
    chain is empty and nothing observable says why.
    """
    reasons = {skip.reason for preflight in emptied[:1] for skip in preflight.skipped}
    for condition in GOVERNING_CONDITION_PRECEDENCE:
        if condition in reasons:
            return condition
    return UNAVAILABLE_EVIDENCE


def _legacy_provider(*, emptied: tuple[NodePreflight, ...]) -> str | None:
    """The vendor whose legacy blanket emptied the FIRST emptied chain.

    Scoped to that one node for the reason `_governing_condition` is, and read
    off the SKIP the filter recorded rather than re-derived from the journal:
    `_legacy_provider` in `_acp_candidate_preflight` records the covering
    provider in the skip's `hold_key` at the moment it decides, so this is the
    one value that cannot disagree with the refusal it accompanies.
    """
    keys = [
        skip.hold_key
        for preflight in emptied[:1]
        for skip in preflight.skipped
        if skip.reason == LEGACY_HOLD_SKIP and skip.hold_key is not None
    ]
    return keys[0] if keys else None


def _confirmation_endings(*, emptied: tuple[NodePreflight, ...]) -> tuple[str, ...]:
    """The ending each confirmation turn reached on the FIRST emptied chain.

    Scoped to that one node for the reason `_governing_condition` is: the
    refusal names ONE admission-required node, and an ending taken from a later
    node would report a turn that was never run for the named one.

    DEDUPLICATED, IN FIRST-SEEN ORDER. Three candidates whose turns were all
    terminated are ONE condition rather than three rows of the same word, and
    the order is the chain's own so a reader sees what the primary did first.

    EMPTY when no turn was run, which the skip records as a `condition` of
    `None` -- see `AvailabilityWait.confirmation_endings` for why that absence
    is kept rather than filled in.
    """
    found: dict[str, None] = {}
    for preflight in emptied[:1]:
        for skip in preflight.skipped:
            if skip.reason == OUTSTANDING_CONFIRMATION_SKIP and skip.condition is not None:
                found.setdefault(skip.condition, None)
    return tuple(found)


def _governing_holds(
    *, emptied: tuple[NodePreflight, ...], holds: tuple[AcpAvailabilityHold, ...]
) -> tuple[GoverningHold, ...]:
    """Every live hold that emptied ANY admission-required chain, deduplicated.

    Keyed by observation id, because one record legitimately skips candidates
    on several nodes and reporting it once per node would make a single outage
    read as several.
    """
    governing: dict[str, GoverningHold] = {}
    for preflight in emptied:
        for skip in preflight.skipped:
            if skip.reason != TYPED_HOLD_SKIP:
                continue
            for hold in holds:
                if _hold_decided_skip(hold=hold, skip=skip):
                    governing[hold.observation_id] = GoverningHold(
                        observation_id=hold.observation_id,
                        scope=hold.scope,
                        hold_key=hold.hold_key,
                        candidate_key=hold.candidate_key,
                        cause=hold.cause,
                        expires_at=hold.expires_at,
                    )
    return tuple(governing.values())


def _hold_decided_skip(*, hold: AcpAvailabilityHold, skip: SkippedCandidate) -> bool:
    """Whether this record is the one that decided this skip.

    A DOMAIN record is matched on scope and hold key alone: it carries no
    candidate key while the skip records the skipped CANDIDATE's own, so
    comparing the two would match no domain hold at all. A CANDIDATE record is
    matched on its exact identity pair, which is the coverage rule it was
    stored under.
    """
    if (hold.scope, hold.hold_key) != (skip.scope, skip.hold_key):
        return False
    if hold.scope == DOMAIN_SCOPE:
        return True
    return hold.candidate_key == skip.candidate_key


def _reevaluate_at(
    *, governing: tuple[GoverningHold, ...], now: datetime, reprobe_interval_seconds: int
) -> str:
    """The earliest governing expiry, or the cadence after this evaluation."""
    expiries = [
        instant
        for hold in governing
        if (instant := parse_hold_instant(text=hold.expires_at)) is not None
    ]
    if not expiries:
        return (now + timedelta(seconds=reprobe_interval_seconds)).strftime(_ISO_FORMAT)
    return min(expiries).strftime(_ISO_FORMAT)
