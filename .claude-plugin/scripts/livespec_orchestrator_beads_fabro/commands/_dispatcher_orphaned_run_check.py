"""The `orphaned-factory-run` Ledger invariant — the fail-closed half.

The standing invariant this asserts: on every declared factory, a non-terminal
Fabro run exists only for a work-item that is `active` under the newest run the
dispatch journal recorded for it. Any other non-terminal run is holding a
scheduler slot for a question the ledger has already answered.

It reads through the reconciler's `--dry-run` machinery rather than re-deriving
the join. This observation-only call opts into goal text as a labeled hint, so
it can flag a run whose launch record is missing; the mutating command repeats
the join with that hint disabled and cannot act without recorded ownership.
Being a dry run it exports nothing, terminates nothing, and journals nothing:
surveying is not an act.

FAIL-CLOSED, and specifically about the unreachable case. A factory that cannot
be surveyed produces its OWN finding rather than an empty orphan set, because
those two observations are indistinguishable in the reconciler's summary shape
and only one of them is good news. Treating an outage as a pass is how a check
whose whole job is to notice held slots comes to report a clean tenant while a
factory it never reached holds several.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import LedgerFinding
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook import (
    dispatch_journal_path,
)

__all__: list[str] = [
    "ORPHANED_FACTORY_RUN_CHECK",
    "orphaned_factory_run_findings",
]

ORPHANED_FACTORY_RUN_CHECK = "orphaned-factory-run"

# The `item_id` a finding carries when it is about a FACTORY rather than about
# one row — the same sentinel the spec and janitor check surfaces already use
# for their repo-scoped findings.
_NO_ITEM = "-"


def orphaned_factory_run_findings(
    *,
    repo: Path,
    runner: CommandRunner | None = None,
) -> list[LedgerFinding]:
    """Survey every declared factory and report the runs the ledger disowns.

    A repo that declares no factory returns no findings and performs no I/O:
    there is no inventory to hold a slot, so there is nothing this invariant
    can be violated by. That is a genuine vacuous pass, distinct from the
    unreachable case below, which is a finding.
    """
    factories = reconcile_factory_targets(repo=repo)
    if not factories:
        return []
    config = store_config(repo=repo)
    journal = dispatch_journal_path(repo=repo)
    summary = reconcile_runs(
        inputs=ReconcileInputs(
            repo=repo,
            fabro_bin=resolve_fabro_bin(cwd=repo),
            id_prefix=config.prefix,
            items=load_items(repo=repo),
            journaled=read_journaled_runs(path=journal),
            runner=ShellCommandRunner() if runner is None else runner,
            # A dry run appends nothing; the writer is supplied because the
            # inputs record requires one, not because this survey writes.
            journal=JournalFile(path=journal),
            ledger=make_beads_client(config=config),
            allow_goal_text_attribution=True,
        ),
        factories=factories,
        dry_run=True,
    )
    return [*_orphan_findings(summary=summary), *_unreachable_findings(summary=summary)]


def _orphan_findings(*, summary: ReconcileRunsSummary) -> list[LedgerFinding]:
    return [
        LedgerFinding(
            check=ORPHANED_FACTORY_RUN_CHECK,
            item_id=run.work_item_id,
            message=(
                f"non-terminal run {run.run_id} ({run.status_kind}) on factory "
                f"{run.factory_name} is attributed via {run.attribution_source} to a "
                "work-item whose ledger status "
                f"is {run.work_item_status!r}, not 'active' ({run.orphan_reason}); "
                f"reconcile it with: dispatcher.py reconcile-runs --factory "
                f"{run.factory_name}"
            ),
        )
        for run in summary.reconciled
    ]


def _unreachable_findings(*, summary: ReconcileRunsSummary) -> list[LedgerFinding]:
    return [
        LedgerFinding(
            check=ORPHANED_FACTORY_RUN_CHECK,
            item_id=_NO_ITEM,
            message=(
                f"factory {error.factory_name} could not be surveyed ({error.reason}): "
                f"{error.detail}; an unreachable factory is reported rather than "
                f"passed, because an unread inventory and an empty one are the same "
                f"observation and only one of them is safe"
            ),
        )
        for error in summary.errors
    ]
