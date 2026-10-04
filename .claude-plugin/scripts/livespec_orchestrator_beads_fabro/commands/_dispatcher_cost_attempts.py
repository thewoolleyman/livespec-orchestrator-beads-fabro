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
    "AttemptCost",
    "AttemptPricer",
    "ChainCost",
    "CostObservation",
    "chain_cost",
]


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


def _spent_tokens(*, tokens: TokenVector) -> bool:
    """Whether this attempt reported any nonzero usage component.

    The contract's unobservability rule turns on a NONZERO component: an
    attempt that reported no usage at all has nothing to price, so leaving it
    unpriced costs the run nothing and must not darken a total the rest of the
    attempts fully account for.
    """
    return (tokens.input + tokens.output + tokens.cache_write + tokens.cache_read) > 0
