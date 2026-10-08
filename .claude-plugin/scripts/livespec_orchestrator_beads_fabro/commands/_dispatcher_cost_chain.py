"""Composing one run's events, its recorded usage and its catalogs into a cost.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run". The
arithmetic lives in `_dispatcher_cost_attempts`, the price resolution in
`_acp_attempt_price`, the attempt windows in `_acp_attempt_windows`; this module
is the only impure part -- it reads the run's event stream from the dispatch's
RESOLVED factory and the dispatch target's committed catalogs -- and it exists
separately so none of those three can reach for I/O of its own.

NO NEW GATE IS BUILT HERE, which is the whole posture. The same section says
section "Fail-closed cost gate (keyed on `--item` presence)" "remains
authoritative", so an unpriceable run arrives at that gate as an ABSENT derived
cost and the branch that has existed since work-item 5v9 decides unchanged:
unattended drain refuses, a hand-picked `--item` dispatch warns. A second
refusal path reading the chain cost directly would be a second policy to keep
in step with the first, and the two would diverge silently because both produce
a well-formed verdict.

EVERY ARM THAT CANNOT ESTABLISH A CHAIN RETURNS `None`, AND THAT IS NOT A
FALLBACK TO ZERO. `None` means "this run's cost was not derived per attempt",
which hands the decision back to the sink's own accumulator -- the path every
dispatch in this fleet is priced by today, and the path "a single-candidate run
is priced exactly as before this change" depends on. The arms that return it are
all cases where the events carry no evidence about candidates: no resolvable
factory, no run id, a failed or unparseable read, a stream with no
`agent.acp.started` records (a pre-chain engine), or no accrued telemetry at
all.

A TERMINALLY UNSUCCESSFUL RUN IS NOT READ AT ALL. "Terminally unsuccessful runs
retain the existing no-cost-observation/no-gate posture", so a non-green outcome
never reaches the events fetch -- which is stronger than discarding its result,
because the fetch is what would make a failed run's partial telemetry available
to be mistaken for an observation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_attempt_price import attempt_price
from livespec_orchestrator_beads_fabro.commands._acp_attempt_windows import (
    AcpAttemptWindow,
    attempt_windows,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpEventScan
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import AcpModelEntry
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import AcpNodeChain
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_projection_run import (
    ACP_EVENTS_TIMEOUT_SECONDS,
    resolve_projection_factory,
)
from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    dispatcher_block,
    resolve_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._config_acp import resolve_acp_catalogs_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ChainCost,
    CostObservation,
    chain_cost,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import ModelPrice
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import (
    CostSink,
    cost_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "chain_costs",
    "run_chain_cost",
]

# Every failure a configuration or ledger read can raise here. The cost path is
# observability that runs AFTER the verdict, so it degrades to "not derived per
# attempt" rather than propagating -- the same fail-soft posture the gate it
# feeds already takes.
_RECOVERABLE = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)

FactoryResolver = Callable[..., FactoryTarget | None]

# The model catalog and the per-node chains, in that order: the two sources the
# contract's resolution order consults, resolved together from one read.
_PricingSources = tuple[Mapping[str, AcpModelEntry], Mapping[str, AcpNodeChain]]


def chain_costs(
    *,
    repo: Path,
    outcomes: tuple[DispatchOutcome, ...],
    sink: CostSink,
    runner: CommandRunner | None = None,
    factory_of: FactoryResolver | None = None,
) -> dict[str, ChainCost]:
    """The per-attempt cost of every GREEN outcome whose run reports a chain.

    Keyed by work-item id, because that is how both the cost gate and the
    report-mode reporter look a cost up. An outcome with no entry is one whose
    cost was not derived per attempt, which is the ordinary case.

    `factory_of` is the per-item factory resolution, injected so a test can
    drive the composition without a committed `.livespec.jsonc`; it defaults to
    the same `resolve_projection_factory` the hold projection uses, so a cost
    read and a hold read of one run always agree about which host to ask.
    """
    resolver = resolve_projection_factory if factory_of is None else factory_of
    costs: dict[str, ChainCost] = {}
    for outcome in outcomes:
        if outcome.status != "green" or outcome.fabro_run_id is None:
            continue
        factory = _resolved_factory(resolver=resolver, repo=repo, outcome=outcome)
        if factory is None:
            continue
        cost = run_chain_cost(
            repo=repo,
            work_item_id=outcome.work_item_id,
            run_id=outcome.fabro_run_id,
            sink=sink,
            factory=factory,
            runner=runner,
        )
        if cost is not None:
            costs[outcome.work_item_id] = cost
    return costs


def run_chain_cost(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    sink: CostSink,
    factory: FactoryTarget,
    runner: CommandRunner | None = None,
) -> ChainCost | None:
    """One run's per-attempt cost, or None when the events establish no chain."""
    windows = _windows(
        repo=repo,
        run_id=run_id,
        factory=factory,
        runner=ShellCommandRunner() if runner is None else runner,
    )
    if not windows:
        return None
    observations = _observations(sink=sink, work_item_id=work_item_id)
    if observations is None:
        return None
    catalog, chains = _pricing_sources(repo=repo)
    return chain_cost(
        observations=observations,
        windows=windows,
        price_of=_pricer(catalog=catalog, chains=chains),
    )


def _resolved_factory(
    *, resolver: FactoryResolver, repo: Path, outcome: DispatchOutcome
) -> FactoryTarget | None:
    """This item's factory, or None when nothing resolves one.

    Wrapped because the resolution reads the ledger and the repository's
    configuration, and a cost that cannot be derived is not a reason to lose
    the wave's verdict.
    """
    resolved = attempt(
        action=lambda: resolver(repo=repo, work_item_id=outcome.work_item_id),
        exceptions=_RECOVERABLE,
    )
    if isinstance(resolved, AttemptFailure) or resolved is None or resolved.server is None:
        return None
    return resolved


def _windows(
    *, repo: Path, run_id: str, factory: FactoryTarget, runner: CommandRunner
) -> tuple[AcpAttemptWindow, ...]:
    """The run's attempt windows, read server-qualified, or `()`.

    The read names the factory the dispatch actually went to. A bare
    invocation answers for the LOCAL server, where this run does not exist --
    a clean, plausible, wrong answer with no error, which here would read as
    "this run executed no chain".
    """
    scan = attempt(
        action=lambda: _scan(repo=repo, run_id=run_id, factory=factory, runner=runner),
        exceptions=_RECOVERABLE,
    )
    if isinstance(scan, AttemptFailure) or scan is None:
        return ()
    return attempt_windows(scan=scan)


def _scan(
    *, repo: Path, run_id: str, factory: FactoryTarget, runner: CommandRunner
) -> AcpEventScan | None:
    """Fetch and read the run's event stream, or None when it is unusable."""
    port = FabroPort(
        fabro_bin=factory_fabro_bin(factory=factory, fallback=resolve_fabro_bin(cwd=repo)),
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=runner,
        cwd=repo,
    )
    events = port.events(run_id=run_id, timeout_seconds=ACP_EVENTS_TIMEOUT_SECONDS)
    if events.command.exit_code != 0:
        return None
    read = scan_acp_events(payload=events.payload)
    return None if isinstance(read, str) else read


def _observations(*, sink: CostSink, work_item_id: str) -> tuple[CostObservation, ...] | None:
    """The run's recorded API calls under the first key that accrued, or None."""
    for key in cost_lookup_keys(work_item_id=work_item_id, dispatch_id=None):
        observations = sink.observations(key=key)
        if observations is not None:
            return observations
    return None


def _pricing_sources(*, repo: Path) -> _PricingSources:
    """The two price sources the contract's resolution order needs, or neither.

    Both come from ONE read, for the reason `_config_acp`'s own docstring gives
    about the catalogs: two independent reads of one file cannot be proven to
    agree, and the disagreement would be silent because each read produces a
    well-formed value.

    Unreadable configuration yields NEITHER source rather than the built-in
    snapshot. That is the fail-closed direction twice over: with no prices
    every attempt goes unpriced and the run cost goes dark, where substituting
    the shipped snapshot would price attempts against a catalog this repository
    may have deliberately overridden -- and report the result as an
    observation.
    """
    sources = attempt(action=lambda: _read_pricing_sources(repo=repo), exceptions=_RECOVERABLE)
    if isinstance(sources, AttemptFailure):
        return ({}, {})
    return sources


def _read_pricing_sources(*, repo: Path) -> _PricingSources:
    """Resolve the model catalog and the per-node chains from one block read."""
    catalogs = resolve_acp_catalogs_for(cwd=repo)
    if isinstance(catalogs, str):
        return ({}, {})
    chains = repository_acp_chains(block=dispatcher_block(cwd=repo), catalogs=catalogs)
    return (catalogs.models, {} if isinstance(chains, str) else chains)


def _pricer(
    *, catalog: Mapping[str, AcpModelEntry], chains: Mapping[str, AcpNodeChain]
) -> Callable[..., ModelPrice | None]:
    """An `AttemptPricer` closing over this dispatch target's committed bytes.

    The per-candidate table is looked up by NODE and candidate index together,
    because two nodes of one run may declare different chains and a table
    keyed on the index alone would price one node's attempt at another's rate.
    """

    def price(*, node: str | None, candidate_index: int | None, identity: str) -> ModelPrice | None:
        return attempt_price(
            raw_model=identity,
            catalog=catalog,
            candidate_pricing=_candidate_pricing(
                chains=chains, node=node, candidate_index=candidate_index
            ),
        )

    return price


def _candidate_pricing(
    *, chains: Mapping[str, AcpNodeChain], node: str | None, candidate_index: int | None
) -> AcpCandidatePricing | None:
    """The explicit table the attempt's own candidate declared, or None.

    Candidate zero's table rides the chain itself -- it is the PRIMARY's -- and
    candidate `n` reads `fallbacks[n - 1]`, which is the ordering the chain
    grammar already uses. An index past the configured chain's end is an
    attempt of a chain this configuration no longer describes, and the honest
    answer there is no table rather than the nearest one.
    """
    if node is None or candidate_index is None:
        return None
    chain = chains.get(node)
    if chain is None:
        return None
    if candidate_index == 0:
        return chain.pricing
    fallback_index = candidate_index - 1
    if fallback_index >= len(chain.fallbacks):
        return None
    return chain.fallbacks[fallback_index].pricing
