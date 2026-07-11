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
    try:
        _cost_gate(
            args=args,
            repo=repo,
            outcomes=outcomes,
            journal=journal,
            runner=resolved_runner,
            poster=poster if poster is not None else HttpNotifyPoster(),
        )
    except Exception as exc:
        # Fail-open supervisor: the verdict is already final, so a broad
        # catch is the whole point — any error is journaled and swallowed,
        # never raised.
        journal.append(
            record={
                "stage": "cost-gate-error",
                "reason": f"{type(exc).__name__}",
            }
        )


def derived_costs(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, int]:
    """The CC-token-derived per-dispatch cost for each green outcome."""
    try:
        return _read_derived_costs(args=args, repo=repo, outcomes=outcomes)
    except Exception:
        # Fail-open: a cost-sink read error degrades to the fail-closed path
        # (gate_wave then sees no derived cost), never crashing the cost gate.
        return {}


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
    ps = runner.run(
        argv=[args.fabro_bin, "ps", "-a", "--json"],
        cwd=repo,
        timeout_seconds=_FABRO_PS_PROBE_TIMEOUT_SECONDS,
    )
    ps_json = ps.stdout if ps.exit_code == 0 else ""
    refusals = gate_wave(
        mode=getattr(args, "mode", "shadow"),
        outcomes=tuple(outcomes),
        ps_json=ps_json,
        journal=journal,
        environ=dict(os.environ),
        derived_cost_micros_by_work_item=derived_costs(args=args, repo=repo, outcomes=outcomes),
        cost_mode=cost_mode,
    )
    if cost_mode == COST_MODE_REPORT:
        _emit_cost_report_telemetry(args=args, repo=repo, outcomes=outcomes)
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


def _emit_cost_report_telemetry(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> None:
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    reports = _derived_reports(args=args, repo=repo, outcomes=outcomes)
    items = tuple(
        build_cost_report_item(
            work_item_id=outcome.work_item_id,
            report=reports.get(outcome.work_item_id),
            default_model=default_model,
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
) -> dict[str, int]:
    sink = CostSink(path=cost_sink_path(args=args, repo=repo))
    derived: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.status != "green":
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
    try:
        return _read_derived_reports(args=args, repo=repo, outcomes=outcomes)
    except Exception:
        # Fail-open: a cost-sink read error degrades the report to
        # all-unobservable, never crashing the cost stage.
        return {}


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
