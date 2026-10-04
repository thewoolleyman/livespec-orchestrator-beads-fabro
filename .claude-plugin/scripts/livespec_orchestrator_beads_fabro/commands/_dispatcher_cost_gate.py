"""Post-verdict cost gate and derived-cost readers for the Dispatcher."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    COST_MODE_REPORT,
    gate_wave,
    resolve_cost_mode,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import ChainCost
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain import chain_costs
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_report import (
    build_cost_report_item,
    emit_cost_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import (
    CostReport,
    CostSink,
    cost_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyEvent,
    NotifyPoster,
    notify_terminal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    cost_report_spans_path,
    cost_sink_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import repo_run_attribution
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = ["cost_gate_after_verdict", "derived_costs"]

_FABRO_PS_PROBE_TIMEOUT_SECONDS = 60.0
_SPEND_CAP_BREACH_CLASS = "spend-cap-breach"


def cost_gate_after_verdict(  # noqa: PLR0913 — kw-only fail-open stage; seams are independently injectable.
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: JournalFile,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Run the fail-open cost gate after the verdict is computed."""
    resolved_runner: CommandRunner = runner if runner is not None else ShellCommandRunner()
    if token_supplier is not None:
        resolved_runner = GithubTokenEnvRunner(inner=resolved_runner, token=token_supplier)
    gated = attempt(
        action=lambda: _cost_gate(
            args=args,
            repo=repo,
            outcomes=outcomes,
            journal=journal,
            runner=resolved_runner,
            poster=poster if poster is not None else HttpNotifyPoster(),
        ),
        exceptions=(AttributeError, OSError, RuntimeError),
    )
    if isinstance(gated, AttemptFailure):
        journal.append(
            record={
                "stage": "cost-gate-error",
                "reason": f"{type(gated.error).__name__}",
            }
        )


def derived_costs(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    chains: dict[str, ChainCost] | None = None,
) -> dict[str, int]:
    """The CC-token-derived per-dispatch cost for each green outcome.

    `chains` is the per-attempt cost of any outcome whose run executed a
    candidate chain, and it SUPERSEDES the sink's own aggregate for that
    outcome — including when it is unobservable, in which case the outcome is
    ABSENT from the result. That absence is the point: the sink's aggregate for
    the same run is a default-priced number, so leaving the gate on it would
    gate on a price no attempt actually ran at, while the report said the cost
    was unobservable. An outcome with no chain entry is read from the sink
    exactly as before.
    """
    derived = attempt(
        action=lambda: _read_derived_costs(
            args=args, repo=repo, outcomes=outcomes, chains={} if chains is None else chains
        ),
        exceptions=(AttributeError, OSError, RuntimeError, ValueError),
    )
    if isinstance(derived, AttemptFailure):
        return {}
    return derived


def _cost_gate(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: JournalFile,
    runner: CommandRunner,
    poster: NotifyPoster,
) -> None:
    if not any(outcome.status == "green" for outcome in outcomes):
        return
    cost_mode = resolve_cost_mode(environ=dict(os.environ))
    ps = FabroPort(
        fabro_bin=args.fabro_bin,
        target=FabroTarget(),
        runner=runner,
        cwd=repo,
    ).ps(timeout_seconds=_FABRO_PS_PROBE_TIMEOUT_SECONDS)
    ps_json = ps.command.stdout if ps.command.exit_code == 0 else ""
    # Resolved ONCE and passed to both consumers: the gate and the report must
    # agree about each run's cost, and two reads of a live event stream cannot
    # be proven to agree — the disagreement would be invisible, because both
    # produce a well-formed cost.
    chains = _chain_costs(args=args, repo=repo, outcomes=outcomes, runner=runner)
    refusals = gate_wave(
        unattended=not bool(getattr(args, "items", None) or getattr(args, "item", None)),
        outcomes=tuple(outcomes),
        ps_json=ps_json,
        journal=journal,
        environ=dict(os.environ),
        derived_cost_micros_by_work_item=derived_costs(
            args=args, repo=repo, outcomes=outcomes, chains=chains
        ),
        cost_mode=cost_mode,
        attribution=repo_run_attribution(repo=repo),
    )
    if cost_mode == COST_MODE_REPORT:
        _emit_cost_report_telemetry(args=args, repo=repo, outcomes=outcomes, chains=chains)
        return
    if not refusals:
        return
    events = tuple(
        NotifyEvent(work_item_id=work_item_id, outcome_class=_SPEND_CAP_BREACH_CLASS)
        for work_item_id in refusals
    )
    notify_terminal(
        events=events,
        run_id=_run_id(),
        poster=poster,
        journal=journal,
    )


def _chain_costs(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    runner: CommandRunner,
) -> dict[str, ChainCost]:
    """The per-attempt cost of every green outcome, or `{}` — never a raise.

    Fail-soft like every other seam in this stage: the cost path runs AFTER the
    verdict, so an unreadable event stream or configuration degrades to "no
    cost derived per attempt" (the sink's own aggregate then decides, exactly
    as before this slice) rather than costing the wave its verdict.
    """
    costs = attempt(
        action=lambda: chain_costs(
            repo=repo,
            outcomes=tuple(outcomes),
            sink=CostSink(path=cost_sink_path(args=args, repo=repo)),
            runner=runner,
        ),
        exceptions=(AttributeError, OSError, RuntimeError, ValueError),
    )
    if isinstance(costs, AttemptFailure):
        return {}
    return costs


def _emit_cost_report_telemetry(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    chains: dict[str, ChainCost],
) -> None:
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    reports = _derived_reports(args=args, repo=repo, outcomes=outcomes)
    items = tuple(
        build_cost_report_item(
            work_item_id=outcome.work_item_id,
            report=reports.get(outcome.work_item_id),
            default_model=default_model,
            chain=chains.get(outcome.work_item_id),
        )
        for outcome in outcomes
        if outcome.status == "green"
    )
    emit_cost_report(
        items=items,
        dispatch_id=_dispatch_id_of(outcomes=outcomes),
        spans_path=cost_report_spans_path(args=args, repo=repo),
    )


def _dispatch_id_of(*, outcomes: list[DispatchOutcome]) -> str | None:
    return None if outcomes else None


def _read_derived_costs(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    chains: dict[str, ChainCost],
) -> dict[str, int]:
    sink = CostSink(path=cost_sink_path(args=args, repo=repo))
    derived: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        chain = chains.get(outcome.work_item_id)
        if chain is not None:
            if chain.usd_micros is not None:
                derived[outcome.work_item_id] = chain.usd_micros
            continue
        for key in cost_lookup_keys(work_item_id=outcome.work_item_id, dispatch_id=None):
            micros = sink.usd_micros(key=key)
            if micros is not None:
                derived[outcome.work_item_id] = micros
                break
    return derived


def _derived_reports(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, CostReport]:
    reports = attempt(
        action=lambda: _read_derived_reports(args=args, repo=repo, outcomes=outcomes),
        exceptions=(AttributeError, OSError, RuntimeError, ValueError),
    )
    if isinstance(reports, AttemptFailure):
        return {}
    return reports


def _read_derived_reports(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, CostReport]:
    sink = CostSink(path=cost_sink_path(args=args, repo=repo))
    reports: dict[str, CostReport] = {}
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        for key in cost_lookup_keys(work_item_id=outcome.work_item_id, dispatch_id=None):
            report = sink.cost_report(key=key)
            if report is not None:
                reports[outcome.work_item_id] = report
                break
    return reports


def _run_id() -> str:
    return uuid.uuid4().hex
