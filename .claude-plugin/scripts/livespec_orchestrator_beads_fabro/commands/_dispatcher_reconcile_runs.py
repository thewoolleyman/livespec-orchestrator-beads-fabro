"""Reconcile every configured factory's non-terminal run inventory.

The invariant: at any moment, on every configured factory, the set of
non-terminal Fabro runs equals the set of ledger items that are `active`
under a claim whose journaled run id is that run. Any other non-terminal run
is an ORPHAN, and reconciling it is a machine act — export its record,
terminate it, journal what happened — with no human in the loop.

Reconciling a run NEVER touches the work-item. Not its status, not its
`blocked_reason`, not its labels. A needs-human decision lives in the ledger
and a human clears it there; what this module removes is a factory-side
scheduler slot held for a question that is already moot, which is a
different object entirely. The ledger seam handed in cannot express those
writes, so the guarantee is structural rather than a convention.

Failure is per-factory and per-run. One unreachable factory journals an
error and the survey continues on the rest, because the alternative — one
outage suppressing reconciliation everywhere — is exactly the silent-hold
failure this command exists to end.

A run parked at a human gate whose item is still live has no moot question to
release it, so it is governed instead by `dispatcher.blocked_run_grace_seconds`
(`_dispatcher_reconcile_runs_grace.py`). Past the grace it becomes an orphan
like any other and takes the same export-then-terminate path; inside it — or
with a park nobody can measure — it is REPORTED as held and left running. The
held set is carried separately from the reconciled set precisely so that
"reported" can never become "terminated" by a later edit.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    export_orphan_reference,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import (
    HeldRun,
    measured_grace,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
    port_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import (
    OrphanRun,
    blocked_grace_candidate_ids,
    classify_blocked_holds,
    classify_orphans,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records import (
    JOURNAL_STAGE_ERROR,
    ReconciledRun,
    ReconcileError,
    ReconcileRunsSummary,
    journal_error,
    journal_export,
    journal_reconciled,
    journal_unauthenticated,
    reconciled_from,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_spans import (
    emit_reconcile_termination_spans,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_terminate import (
    terminate_orphan_run,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "JOURNAL_STAGE_ERROR",
    "ReconcileError",
    "ReconcileRunsSummary",
    "ReconciledRun",
    "reconcile_runs",
]

_PS_TIMEOUT_SECONDS = 60.0
_ERROR_NO_SERVER_URL = "factory-server-url-missing"
_ERROR_PS_FAILED = "factory-ps-failed"
_ERROR_EXPORT_FAILED = "export-not-verified"


def reconcile_runs(
    *,
    inputs: ReconcileInputs,
    factories: Sequence[FactoryTarget],
    dry_run: bool = False,
) -> ReconcileRunsSummary:
    """Survey every factory, reconciling the orphans the ledger disowns."""
    item_statuses = {item.id: item.status for item in inputs.items}
    reconciled: list[ReconciledRun] = []
    errors: list[ReconcileError] = []
    held: list[HeldRun] = []
    for factory in factories:
        if factory.server is None:
            errors.append(
                ReconcileError(
                    factory_name=factory.name,
                    factory_server_url=None,
                    run_id=None,
                    work_item_id=None,
                    reason=_ERROR_NO_SERVER_URL,
                    detail=(
                        f"factory {factory.name} declares no server url; a bare Fabro "
                        f"target would survey whichever server the client defaults to"
                    ),
                )
            )
            continue
        held.extend(
            _reconcile_one_factory(
                inputs=inputs,
                factory=factory,
                item_statuses=item_statuses,
                dry_run=dry_run,
                reconciled=reconciled,
                errors=errors,
            )
        )
    if not dry_run:
        for error in errors:
            journal_error(journal=inputs.journal, error=error)
    return ReconcileRunsSummary(
        reconciled=tuple(reconciled),
        errors=tuple(errors),
        dry_run=dry_run,
        held=tuple(held),
    )


def _reconcile_one_factory(
    *,
    inputs: ReconcileInputs,
    factory: FactoryTarget,
    item_statuses: dict[str, str],
    dry_run: bool,
    reconciled: list[ReconciledRun],
    errors: list[ReconcileError],
) -> tuple[HeldRun, ...]:
    """Reconcile one factory's orphans, returning the runs it is still holding."""
    port = port_for(inputs=inputs, factory=factory)
    ps = port.ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if ps.command.exit_code != 0:
        errors.append(
            ReconcileError(
                factory_name=factory.name,
                factory_server_url=factory.server,
                run_id=None,
                work_item_id=None,
                reason=_ERROR_PS_FAILED,
                detail=f"fabro ps exited {ps.command.exit_code}",
            )
        )
        return ()
    inventory = FactoryRunInventory(
        runs=ps.runs,
        item_statuses=item_statuses,
        journaled=inputs.journaled,
        id_prefix=inputs.id_prefix,
        factory_name=factory.name,
        factory_server_url=str(factory.server),
        attribution=inputs.attribution,
        only_work_item_id=inputs.only_work_item_id,
        allow_goal_text_attribution=inputs.allow_goal_text_attribution,
    )
    grace = measured_grace(
        port=port,
        run_ids=blocked_grace_candidate_ids(inventory=inventory),
        grace_seconds=inputs.blocked_run_grace_seconds,
        now_epoch=inputs.now_epoch,
    )
    for orphan in classify_orphans(inventory=inventory, grace=grace):
        if inputs.only_work_item_id is not None and orphan.work_item_id != inputs.only_work_item_id:
            continue
        outcome = _reconcile_one_run(inputs=inputs, port=port, orphan=orphan, dry_run=dry_run)
        if isinstance(outcome, ReconcileError):
            errors.append(outcome)
            continue
        reconciled.append(outcome)
    return classify_blocked_holds(inventory=inventory, grace=grace)


def _reconcile_one_run(
    *,
    inputs: ReconcileInputs,
    port: FabroPort,
    orphan: OrphanRun,
    dry_run: bool,
) -> ReconciledRun | ReconcileError:
    if dry_run:
        return reconciled_from(orphan=orphan, termination=None, export_comment_id=None)
    export = export_orphan_reference(
        orphan=orphan,
        repo=inputs.repo,
        fabro_bin=inputs.fabro_bin,
        runner=inputs.runner,
        ledger=inputs.ledger,
    )
    if not export.exported:
        return ReconcileError(
            factory_name=orphan.factory_name,
            factory_server_url=orphan.factory_server_url,
            run_id=orphan.run_id,
            work_item_id=orphan.work_item_id,
            reason=_ERROR_EXPORT_FAILED,
            detail=export.detail,
        )
    if export.journal_body is not None:
        journal_export(journal=inputs.journal, orphan=orphan, body=export.journal_body)
    if port.server_api().bearer_token() is None:
        journal_unauthenticated(journal=inputs.journal, orphan=orphan)
    termination = terminate_orphan_run(
        port=port,
        run_id=orphan.run_id,
        status_kind=orphan.status_kind,
    )
    run = reconciled_from(
        orphan=orphan,
        termination=termination,
        export_comment_id=export.comment_id,
    )
    journal_reconciled(journal=inputs.journal, run=run)
    if inputs.telemetry_spans_path is not None and inputs.cancelling_actor is not None:
        emit_reconcile_termination_spans(
            run=run,
            cancelling_actor=inputs.cancelling_actor,
            spans_path=inputs.telemetry_spans_path,
            now_ns=time.time_ns(),
        )
    return run
