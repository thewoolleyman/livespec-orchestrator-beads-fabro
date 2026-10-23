"""A fallback run's cost: every attempt attributed to its window, every one summed.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run": "Token
use and elapsed time MUST be attributed and summed per candidate attempt,
including failed attempts before the successful fallback. ... If any nonzero
usage component cannot be priced, the whole run cost is unobservable, not a
known partial subtotal."

PURE, AND THAT IS WHAT MAKES THE ATTRIBUTION TESTABLE. Observations come from
the cost sink and windows from the run's event stream; both arrive as values,
and the price arrives as a callable. So every attribution rule below is driven
by synthetic timelines in the hermetic tier rather than by staging a real
fallback at a provider -- which nothing in this repository can make happen on
demand, because it needs a live allowance outage.

NOTHING IS DROPPED AND NOTHING IS GUESSED, which are the two opposite failure
directions and the reason attribution returns a window rather than filtering.
An observation inside an attempt's measured window belongs to that attempt. One
in the gap between a measured end and the next start -- engine teardown --
belongs to the attempt that was most recently running, because dropping it
UNDER-REPORTS a real charge. One the events cannot place at all (a legacy sink
record with no instant, or a node no window covers) still reaches the total
with NO candidate attributed, because inventing a candidate for it would price
it at some other candidate's table.

AN UNPRICEABLE COMPONENT POISONS THE WHOLE TOTAL, deliberately. The alternative
-- summing what could be priced -- produces a number smaller than the truth
that reads exactly like a complete observation. A `None` total is the only
honest answer, and it is what routes the run through the fail-closed cost gate.

THE ATTEMPT-COST RECORD BELOW IS THE SAME SECTION'S "Cost follows every
attempt" paragraph, which widens the accounting past the successful run this
module opened with: "For every run released under 'Provider-limit release and
re-dispatch', and for every availability confirmation turn, the Dispatcher MUST
journal one attempt-cost record carrying the attempt's token use and elapsed
time per node attempt wherever the run record exposes them, priced under the
rules below, or marked cost-unobservable. ... Each run or probe cost
observation MUST have a stable identity and MUST be counted at most once across
reconciliation and resume. ... Attempt-cost records are observations only and
never yield a gate verdict."

IT IS A RECORD AND NOT A GATE, which is the one property every reader of it
depends on. `_dispatcher_cost_sequence` folds these rows into a sequence total
and returns no verdict; the fail-closed gate of section "Fail-closed cost gate
(keyed on `--item` presence)" keeps reading only successful runs with a
confirmed run record, and nothing here reaches it. A record that could refuse a
dispatch would make a terminally unsuccessful run -- the only kind that is
released -- gateable, which the same paragraph forbids in as many words.

THE RECORD IS RENDERED HERE AND APPENDED BY ITS TWO CALLERS, the same
decide/record/perform split `_acp_failure_classifier` /
`_acp_hold_records` / `_acp_hold_ledger` take: this module stays pure, so every
field below is exercisable with no journal, no factory and no provider, while
`_dispatcher_provider_limit_disposition` and the availability confirmation turn
each decide WHEN one lands.

TWO FIGURES ARE STATED ABSENT PER ATTEMPT RATHER THAN OMITTED OR ZEROED, and
that is the clause's "wherever the run record exposes them" read honestly. No
engine this fleet runs reports a per-node usage struct -- `fabro inspect`'s
per-node `usage` slot is null on every node and `total_usd_micros` is null on
every run of the pinned build -- so an entry carries the engine's OWN elapsed
measurement and explicit nulls for the token use and the per-attempt price. An
omitted key is what a record from a build predating this clause looks like, so a
reader could not tell an engine that exposed nothing from a record minted before
anyone asked; a zero would be worse again, because zero is a MEASURED figure
everywhere else in this tree and reads as observable.

THE WHOLE-RUN FIGURE IS THE ENGINE'S OWN AND IS NEVER TAKEN FROM THE HOST COST
SINK, which is the decision most likely to be "improved" into a double count.
The sink accrues per WORK ITEM rather than per run -- `cost_lookup_keys` keys on
`work.item.id` first and `CostSink.observations` answers from the first key that
accrued -- so an item released twice would have its first run's calls attributed
to the second run's attempt windows by `_window_for`'s preceding-window arm, and
the sequence fold would then count that spend twice. "MUST be counted at most
once across reconciliation and resume" forbids exactly that, so the record
reports the engine's figure or nothing. It becomes priced the moment the engine
populates `total_usd_micros`, with no change here, exactly as
`observe_run_cost` reads the same field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_attempt_windows import AcpAttemptWindow
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    ModelPrice,
    TokenVector,
    price_at,
)

__all__: list[str] = [
    "ATTEMPT_COST_CONFIRMATION_TURN",
    "ATTEMPT_COST_RELEASED_RUN",
    "ATTEMPT_COST_STAGE",
    "AttemptCost",
    "AttemptPricer",
    "ChainCost",
    "CostObservation",
    "attempt_cost_identity",
    "attempt_cost_record",
    "chain_cost",
]

# The ONE journal stage every attempt-cost record is appended under, whatever
# produced it. One stage rather than one per source, so a fold asking "what did
# this item's released attempts cost" asks a single question and reads the
# source off a field -- the same shape `HOLD_STAGE` takes for observations.
ATTEMPT_COST_STAGE = "attempt-cost"

# The two things the clause says yield a record. They are FIELD VALUES rather
# than two stages for the reason above, and they are part of the identity below
# because a release and a confirmation turn are different attempts even when
# they somehow name one run.
ATTEMPT_COST_RELEASED_RUN = "provider-limit-released-run"
ATTEMPT_COST_CONFIRMATION_TURN = "availability-confirmation-turn"


@dataclass(frozen=True, kw_only=True)
class CostObservation:
    """One distinct API call's observed usage, as the cost sink recorded it.

    `started_at_ms` and `model_identity` are both nullable because a record
    written before this slice carries neither, and a span can arrive with no
    `model` attribute at all -- which is the real Claude Code shape the legacy
    default-model fallback existed for. An absence here is an absence
    downstream, never a substitute.
    """

    dedup_key: str
    started_at_ms: int | None
    model_identity: str | None
    tokens: TokenVector
    node_id: str | None


class AttemptPricer(Protocol):
    """How one attempt's price is resolved, given its candidate and its identity.

    A callable rather than a catalog plus a table, because the resolution ORDER
    is a contract rule of its own (`_acp_attempt_price`) and this module must
    not be able to re-derive it a second way.

    `node` and `candidate_index` together name the attempt's candidate, and
    both are needed: two nodes of one run may declare different chains, so a
    per-candidate explicit table keyed on the index alone would price one
    node's attempt at another's rate. Both are None for an observation no
    window placed -- there is no candidate, so no explicit table applies and
    only the catalog can price it.
    """

    def __call__(
        self, *, node: str | None, candidate_index: int | None, identity: str
    ) -> ModelPrice | None: ...


@dataclass(frozen=True, kw_only=True)
class AttemptCost:
    """One candidate attempt's own usage, elapsed time and cost.

    `usd_micros` is None when this attempt's identity could not be priced,
    which is distinct from zero: zero is a priced attempt that spent nothing.
    `elapsed_ms` is the engine's own measurement of the attempt, absent for the
    attempt that succeeded (nothing recorded a transition away from it).
    """

    node: str | None
    node_visit: int | None
    candidate_index: int | None
    identity: str | None
    tokens: TokenVector
    elapsed_ms: int | None
    usd_micros: int | None


@dataclass(frozen=True, kw_only=True)
class ChainCost:
    """One run's cost, summed across every attempt, or unobservable.

    `usd_micros` is None both when nothing accrued (the dark condition) and
    when any attempt with nonzero usage could not be priced (the no-default
    rule). Both are "this run's cost is not observable", which is the one thing
    the fail-closed gate downstream acts on, so they are deliberately the same
    value rather than two states a caller has to remember to handle alike.

    `priced_identities` names every model that was charged, in attempt order,
    and `model_resolved` is False when ANY attempt was unpriceable -- the two
    fields the cost report's `model_basis` and `model_resolved` are built from.
    """

    usd_micros: int | None
    priced_identities: tuple[str, ...]
    model_resolved: bool
    attempts: tuple[AttemptCost, ...]


def chain_cost(
    *,
    observations: tuple[CostObservation, ...],
    windows: tuple[AcpAttemptWindow, ...],
    price_of: AttemptPricer,
) -> ChainCost:
    """Attribute every observation to an attempt, price each, and sum the run."""
    attempts = _attempts(observations=observations, windows=windows, price_of=price_of)
    unpriced_usage = any(
        _spent_tokens(tokens=attempt.tokens) and attempt.usd_micros is None for attempt in attempts
    )
    observable = len(attempts) > 0 and not unpriced_usage
    return ChainCost(
        usd_micros=sum(attempt.usd_micros or 0 for attempt in attempts) if observable else None,
        priced_identities=_priced_identities(attempts=attempts),
        model_resolved=all(attempt.usd_micros is not None for attempt in attempts),
        attempts=attempts,
    )


def _attempts(
    *,
    observations: tuple[CostObservation, ...],
    windows: tuple[AcpAttemptWindow, ...],
    price_of: AttemptPricer,
) -> tuple[AttemptCost, ...]:
    """One `AttemptCost` per (attempt window, emitted identity) pair.

    Keyed on the identity as well as the window because an attempt that
    re-negotiated its model mid-visit would otherwise have two models' usage
    summed at one price. Splitting is safe -- the totals add up either way --
    and it keeps `priced_identities` able to name every model charged.
    """
    grouped: dict[tuple[AcpAttemptWindow | None, str | None], TokenVector] = {}
    for observation in observations:
        window = _window_for(observation=observation, windows=windows)
        key = (window, observation.model_identity)
        grouped[key] = _add(left=grouped.get(key), right=observation.tokens)
    costs = [
        _attempt_cost(window=window, identity=identity, tokens=tokens, price_of=price_of)
        for (window, identity), tokens in grouped.items()
    ]
    return tuple(sorted(costs, key=_attempt_order))


def _attempt_cost(
    *,
    window: AcpAttemptWindow | None,
    identity: str | None,
    tokens: TokenVector,
    price_of: AttemptPricer,
) -> AttemptCost:
    """One attempt's record, priced through the caller's resolution order."""
    index = None if window is None else window.candidate_index
    node = None if window is None else window.node
    price = (
        None if identity is None else price_of(node=node, candidate_index=index, identity=identity)
    )
    return AttemptCost(
        node=node,
        node_visit=None if window is None else window.node_visit,
        candidate_index=index,
        identity=identity,
        tokens=tokens,
        elapsed_ms=None if window is None else window.elapsed_ms,
        usd_micros=None if price is None else price_at(tokens=tokens, price=price),
    )


def _window_for(
    *, observation: CostObservation, windows: tuple[AcpAttemptWindow, ...]
) -> AcpAttemptWindow | None:
    """The attempt one observation belongs to, or None when it cannot be placed."""
    if observation.started_at_ms is None:
        return None
    scoped = _scoped_windows(observation=observation, windows=windows)
    if not scoped:
        return None
    moment = observation.started_at_ms
    containing = [window for window in scoped if _contains(window=window, moment=moment)]
    if containing:
        return containing[-1]
    preceding = [window for window in scoped if window.started_at_ms <= moment]
    # An observation preceding every recorded start is the first attempt's work
    # by every other piece of evidence: clock skew between the sandbox's agent
    # process and the engine's event stream is real, and the alternative is to
    # drop a charge that demonstrably happened.
    return preceding[-1] if preceding else scoped[0]


def _scoped_windows(
    *, observation: CostObservation, windows: tuple[AcpAttemptWindow, ...]
) -> tuple[AcpAttemptWindow, ...]:
    """The windows an observation could belong to, ordered by start instant.

    An observation naming a node is scoped to THAT node's attempts: two nodes
    of one run overlap on the clock, so an unscoped timeline would attribute a
    review call to an implement candidate. A node no window covers scopes to
    nothing, which leaves the observation counted and unattributed rather than
    attached to the wrong node's candidate.
    """
    candidates = (
        windows
        if observation.node_id is None
        else tuple(window for window in windows if window.node == observation.node_id)
    )
    return tuple(sorted(candidates, key=lambda window: window.started_at_ms))


def _contains(*, window: AcpAttemptWindow, moment: int) -> bool:
    """Whether `moment` falls inside this attempt's own window.

    Half-open: an observation exactly at an attempt's measured end belongs to
    whatever ran next, not to the attempt that had already finished.
    """
    if moment < window.started_at_ms:
        return False
    return window.ended_at_ms is None or moment < window.ended_at_ms


def _priced_identities(*, attempts: tuple[AttemptCost, ...]) -> tuple[str, ...]:
    """Every identity that was charged, in attempt order, each named once."""
    named: list[str] = []
    for attempt in attempts:
        if attempt.identity is not None and attempt.identity not in named:
            named.append(attempt.identity)
    return tuple(named)


def _attempt_order(attempt: AttemptCost) -> tuple[int, str, int, int, str]:
    """A total order over attempts that tolerates the unplaced ones.

    Placed attempts come first, in node / visit / candidate order; the unplaced
    bucket sorts last. Every component is substituted rather than left None,
    because a tuple mixing None and int is not orderable at all and the
    exception would surface as a crashed cost report rather than as a bad one.
    """
    placed = 0 if attempt.candidate_index is not None else 1
    return (
        placed,
        attempt.node or "",
        attempt.node_visit or 0,
        attempt.candidate_index or 0,
        attempt.identity or "",
    )


def _add(*, left: TokenVector | None, right: TokenVector) -> TokenVector:
    """Two token vectors summed category by category."""
    if left is None:
        return right
    return TokenVector(
        input=left.input + right.input,
        output=left.output + right.output,
        cache_write=left.cache_write + right.cache_write,
        cache_read=left.cache_read + right.cache_read,
    )


def attempt_cost_identity(
    *, source: str, factory: str, run_id: str | None, node_attempt: str
) -> str:
    """The stable identity one attempt-cost observation is counted under.

    REPRODUCIBLE AND DISCRIMINATING, and neither half is worth anything alone.
    A constant reproduces perfectly and collapses two releases of one item onto
    one observation, losing a real charge; a counter or a clock discriminates
    perfectly and makes every replay a second observation, double-counting the
    sequence the dedupe exists to protect. So the identity is derived from the
    attempt's own four facts and from nothing else, which is also what lets
    reconciliation re-derive it from the same terminal.

    The three run fields are exactly the `factory:run:node attempt` triple
    `ProviderLimitRelease.release_key` is keyed by, which is the key the clause
    makes a release's own replay idempotent on -- so a release and its
    attempt-cost record cannot come to disagree about which attempt they
    describe.
    """
    return f"{source}:{factory}:{run_id}:{node_attempt}"


def attempt_cost_record(  # noqa: PLR0913 — kw-only record fields: the attempt's four identifying facts, the item it is charged to, the instant, what the run record exposed per attempt, and the engine's own figure. Grouping any pair into a carrier would invent a relationship the row does not have.
    *,
    source: str,
    work_item_id: str,
    factory: str,
    run_id: str | None,
    node_attempt: str,
    occurred_at: str,
    windows: tuple[AcpAttemptWindow, ...],
    usd_micros: int | None,
) -> dict[str, object]:
    """The one appendable row one released run or confirmation turn is costed as.

    `work_item_id` is the ONE item this attempt is charged to, which is the
    clause's "A shared availability probe MUST NOT be charged in full to
    multiple items": a confirmation turn run inside one item's admission
    evaluation establishes availability every peer then benefits from, and the
    record names only the item that spent it, so `_dispatcher_cost_sequence`'s
    per-item fold counts it once and no peer's sequence counts it at all.

    `usd_micros` is the engine's whole-run figure or `None`, and
    `cost_observable` states which -- never inferred by a reader from the value,
    because a figure of zero is a measured figure and reads as observable.
    """
    return {
        "stage": ATTEMPT_COST_STAGE,
        "observation_id": attempt_cost_identity(
            source=source, factory=factory, run_id=run_id, node_attempt=node_attempt
        ),
        "source": source,
        "work_item_id": work_item_id,
        "factory": factory,
        "run_id": run_id,
        "node_attempt": node_attempt,
        "occurred_at": occurred_at,
        "attempts": [_attempt_entry(window=window) for window in windows],
        "usd_micros": usd_micros,
        "cost_observable": usd_micros is not None,
    }


def _attempt_entry(*, window: AcpAttemptWindow) -> dict[str, object]:
    """One node attempt, as the run record exposes it.

    `elapsed_ms` is the engine's OWN measurement and is `None` for the attempt
    nothing bounded, which `AcpAttemptWindow` is careful never to back-fill from
    the window's boundaries. `token_use` and `usd_micros` are stated absent per
    the module docstring: no engine this fleet runs exposes either per node
    attempt, and omitting the keys or writing zeros would both report that
    absence as something else.
    """
    return {
        "node": window.node,
        "node_visit": window.node_visit,
        "candidate_index": window.candidate_index,
        "elapsed_ms": window.elapsed_ms,
        "token_use": None,
        "usd_micros": None,
    }


def _spent_tokens(*, tokens: TokenVector) -> bool:
    """Whether this attempt reported any nonzero usage component.

    The contract's unobservability rule turns on a NONZERO component: an
    attempt that reported no usage at all has nothing to price, so leaving it
    unpriced costs the run nothing and must not darken a total the rest of the
    attempts fully account for.
    """
    return (tokens.input + tokens.output + tokens.cache_write + tokens.cache_read) > 0
