"""The `reconcile-runs` dispatcher subcommand.

It subsumes the narrower per-factory sweep that preceded it, which surveyed
one factory, considered only `runnable` and `running` runs, and skipped any
run whose item it could not find — three filters that together let a run
parked at the human gate hold a scheduler slot indefinitely. That sweep's
name was carried for a while as an alias so the host timer could be renamed
without a flag day; the timer now names this command, so the alias is gone
and the old name fails as an ordinary unknown subcommand.

`--dry-run --json` is the read-only projection: it emits the orphan set and
performs no export, no termination, and no journal write, so a caller can
render "orphaned factory runs" without the survey itself being an act.

The projection carries a second lane beside the orphans: the parked runs the
grace arm is still HOLDING, each with the seconds it has left. A hold that
nothing renders is indistinguishable from a run nobody is watching, which is
the failure the grace arm exists to bound, so the held lane is emitted on
every run — dry or not.

`--dry-run --json` is the read-only projection over the FACTORY: it emits the
orphan set and performs no export, no termination, and no per-run journal
write, so a caller can render "orphaned factory runs" without the survey
itself being an act.

Every invocation nonetheless leaves ONE `reconcile-runs-pass` record, through
the same `journal_reconcile_pass` the dispatch path's wired pass writes
through — a dry run included, flagged as one. This command is what the host
timer invokes, so a record written only by the dispatch path leaves every tick
of that timer invisible: a pass that surveyed both factories and found nothing
is then byte-identical to a unit that never started, which is precisely the
absence the record exists to rule out.

For the same reason a pass that surveyed NO factory is a failure and not a
clean sweep. An unresolvable factories table, an unreadable config, or a
`--factory` naming nobody all reconcile nothing, and "nothing to reconcile"
and "nothing was looked at" are the same empty output with opposite meanings.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import invoker_from_args
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    calibration_spans_path,
    journal_path,
    store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import (
    ReconcileRunsSummary,
    reconcile_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    reconcile_factory_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import (
    DEFAULT_BLOCKED_RUN_GRACE_SECONDS,
    resolve_blocked_run_grace_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_pass import (
    ReconcilePassSummary,
    journal_reconcile_pass,
    reconcile_pass_summary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_spans import (
    emit_reconcile_pass_span,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import (
    repo_run_attribution,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["run_reconcile_runs_command"]

_NO_FACTORY_LINE = (
    "ERROR   (none)  no-factory-surveyed: this pass surveyed no factory, so it "
    "reconciled nothing and observed nothing\n"
)


def run_reconcile_runs_command(*, args: argparse.Namespace) -> int:
    """Reconcile every configured factory, or report why one could not be."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    store = store_config(repo=repo)
    journal = JournalFile(
        path=journal_path(args=args, repo=repo),
        identity=invoker_from_args(args=args),
    )
    factories = reconcile_factory_targets(repo=repo, factory=args.factory)
    summary = reconcile_runs(
        inputs=ReconcileInputs(
            repo=repo,
            fabro_bin=(
                args.fabro_bin if args.fabro_bin is not None else resolve_fabro_bin(cwd=repo)
            ),
            id_prefix=store.prefix,
            items=load_items(repo=repo),
            journaled=read_journaled_runs(path=journal.path),
            runner=ShellCommandRunner(),
            journal=journal,
            ledger=make_beads_client(config=store),
            attribution=repo_run_attribution(repo=repo),
            telemetry_spans_path=calibration_spans_path(args=args, repo=repo),
            cancelling_actor=journal.identity.invoker,
            blocked_run_grace_seconds=unsafe_perform_io(
                resolve_blocked_run_grace_seconds(cwd=repo).value_or(
                    DEFAULT_BLOCKED_RUN_GRACE_SECONDS
                )
            ),
        ),
        factories=factories,
        dry_run=args.dry_run,
    )
    record = reconcile_pass_summary(factories=factories, summary=summary)
    journal_reconcile_pass(journal=journal, summary=record)
    emit_reconcile_pass_span(
        summary=record,
        tenant=store.prefix,
        cancelling_actor=journal.identity.invoker,
        spans_path=calibration_spans_path(args=args, repo=repo),
        now_ns=time.time_ns(),
    )
    _emit(summary=summary, record=record, as_json=args.as_json)
    return 1 if _has_failure(summary=summary, record=record) else 0


def _has_failure(*, summary: ReconcileRunsSummary, record: ReconcilePassSummary) -> bool:
    if record.factories_surveyed == 0:
        return True
    if summary.errors:
        return True
    return any(not run.termination_succeeded for run in summary.reconciled)


def _emit(
    *,
    summary: ReconcileRunsSummary,
    record: ReconcilePassSummary,
    as_json: bool,
) -> None:
    if as_json:
        payload = {
            "dry_run": summary.dry_run,
            "errors": [asdict(error) for error in summary.errors],
            "held": [asdict(run) for run in summary.held],
            "factories_surveyed": record.factories_surveyed,
            "factory_names": list(record.factory_names),
            "reconciled": [asdict(run) for run in summary.reconciled],
        }
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if record.factories_surveyed == 0:
        # Returning here rather than falling through to the orphan lines below
        # is not an optimisation: with nothing surveyed both loops are empty by
        # construction, and the "(no orphaned fabro runs found)" line they lead
        # to is the exact false reassurance this branch exists to withhold.
        _ = write_stdout(text=_NO_FACTORY_LINE)
        return
    for error in summary.errors:
        _ = write_stdout(text=f"ERROR   {error.factory_name}  {error.reason}: {error.detail}\n")
    for run in summary.reconciled:
        _ = write_stdout(
            text=(
                f"ORPHAN  {run.work_item_id}  {run.run_id}  factory={run.factory_name} "
                f"run={run.status_kind} item={run.work_item_status} "
                f"reason={run.orphan_reason} route={run.termination_route}\n"
            )
        )
    for run in summary.held:
        _ = write_stdout(
            text=(
                f"HELD    {run.work_item_id}  {run.run_id}  factory={run.factory_name} "
                f"run={run.status_kind} item={run.work_item_status} "
                f"reason={run.hold_reason} remaining={run.seconds_remaining}\n"
            )
        )
    if not summary.errors and not summary.reconciled and not summary.held:
        _ = write_stdout(text="(no orphaned fabro runs found)\n")
