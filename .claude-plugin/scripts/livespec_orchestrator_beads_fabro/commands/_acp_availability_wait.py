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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    HEADROOM_SKIP,
    LEGACY_HOLD_SKIP,
    PROBE_SKIP,
    TYPED_HOLD_SKIP,
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
    "GOVERNING_CONDITION_PRECEDENCE",
    "UNAVAILABLE_EVIDENCE",
    "AvailabilityWait",
    "GoverningHold",
    "availability_wait",
]

# The condition a refusal names when no skip on the emptied node named one.
# "When no hold governs the refusal, it MUST name the outstanding
# confirmation, unavailable evidence source, admission-time credential-probe
# skip, or admission session-headroom skip instead."
UNAVAILABLE_EVIDENCE = "unavailable-availability-evidence"

# Which skip governs when several emptied one chain. A DURABLE record outranks
# an ephemeral one because it is the fact carrying a bounded expiry and the one
# an operator can clear; the typed record outranks the legacy blanket for the
# same reason the filter consults it first.
GOVERNING_CONDITION_PRECEDENCE: tuple[str, ...] = (
    TYPED_HOLD_SKIP,
    LEGACY_HOLD_SKIP,
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
    """The scheduled reevaluation one emptied-chain evaluation produced."""

    node: str
    nodes: tuple[str, ...]
    governing_condition: str
    reevaluate_at: str
    holds: tuple[GoverningHold, ...]
    unobservable_observations: int


def availability_wait(
    *,
    verdict: AcpPreflightVerdict,
    holds: tuple[AcpAvailabilityHold, ...],
    now_iso: str,
    reprobe_interval_seconds: int,
) -> AvailabilityWait | None:
    """Schedule the next admission evaluation, or `None` when none is owed.

    `None` means there is nothing to look again for: either every
    admission-required chain still holds a candidate, or the verdict is a
    configuration refusal that waiting cannot repair, or the evaluation clock
    itself could not be read.
    """
    if verdict.refusal is not None or not verdict.exhausted:
        return None
    now = parse_hold_instant(text=now_iso)
    if now is None:
        return None
    # Ordered by `exhausted` rather than by `verdict.nodes`, because the named
    # node must be the first EMPTIED one in graph order. Every exhausted node
    # has a preflight by construction -- `_exhausted` is computed from them --
    # so a missing one is a bug and raises rather than being filtered away.
    by_node = {preflight.node: preflight for preflight in verdict.nodes}
    emptied = tuple(by_node[node] for node in verdict.exhausted)
    governing = _governing_holds(emptied=emptied, holds=holds)
    return AvailabilityWait(
        node=verdict.exhausted[0],
        nodes=verdict.exhausted,
        governing_condition=_governing_condition(emptied=emptied),
        reevaluate_at=_reevaluate_at(
            governing=governing, now=now, reprobe_interval_seconds=reprobe_interval_seconds
        ),
        holds=governing,
        unobservable_observations=len(verdict.unobservable),
    )


def _governing_condition(*, emptied: tuple[NodePreflight, ...]) -> str:
    """What emptied the FIRST emptied chain, by the precedence above.

    Scoped to that one node rather than to every emptied node, because the
    refusal names ONE admission-required node and the condition has to be the
    condition of that node -- a precedence taken across the whole set would
    report a typed hold on a later node as the reason the named one is empty.
    """
    reasons = {skip.reason for skip in emptied[0].skipped}
    for condition in GOVERNING_CONDITION_PRECEDENCE:
        if condition in reasons:
            return condition
    return UNAVAILABLE_EVIDENCE


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
