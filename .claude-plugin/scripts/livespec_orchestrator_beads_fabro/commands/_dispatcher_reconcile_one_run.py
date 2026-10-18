"""Disposing of ONE orphan run: export it, re-confirm, then terminate it.

Split out of `_dispatcher_reconcile_runs` by cohesion. That module SURVEYS —
it walks the declared factories, takes each one's inventory, and classifies
every row — while this one is what becomes of a single row the survey decided
is an orphan. The two were together while the survey was small; keeping them
together now hides a sequence whose ORDER is the whole safety argument.

THE ORDER IS THE SAFETY ARGUMENT, so it is stated once here rather than read
off the body. Export, ledger write and read-back are an unconditional
precondition of termination, and the supersession reading is re-taken AFTER
all three — because a sibling dispatch can stamp this run while the export is
in flight, and a reading taken before that work would send a stale verdict
into the one destructive route in the reconciler. A held reading returns
`None`, which is neither an orphan reconciled nor an error: the pass declined
to act, and `supersession_held` records why.

A DRY RUN RETURNS THE PROJECTION AND TOUCHES NOTHING, which is why it returns
before the export rather than guarding each write: a dry pass that exported,
wrote a ledger comment and then declined only the `fabro rm` would have
performed two thirds of an act it reports as not having happened.
"""

from __future__ import annotations

import time

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    export_orphan_reference,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records import (
    ReconciledRun,
    ReconcileError,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_supersession import (
    supersession_held,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = ["reconcile_one_run"]

_ERROR_EXPORT_FAILED = "export-not-verified"


def reconcile_one_run(
    *,
    inputs: ReconcileInputs,
    port: FabroPort,
    orphan: OrphanRun,
    dry_run: bool,
) -> ReconciledRun | ReconcileError | None:
    """Export, re-confirm and terminate one orphan, or report why it was not.

    `None` is the HELD outcome and is neither a reconciliation nor an error:
    the supersession reading this pass opened with was not reproduced, so
    another dispatch now owns the item and the newest run must be left alone.
    """
    if dry_run:
        return reconciled_from(orphan=orphan, termination=None, export_comment_id=None)
    export = export_orphan_reference(
        orphan=orphan,
        repo=inputs.repo,
        # The PORT's client, not the bundle's global one. The export runs
        # `fabro dump --server <this orphan's factory>`, so it is a call
        # against a NAMED factory and takes that factory's client for the
        # same reason every other verb on this port does.
        fabro_bin=port.fabro_bin,
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
    # Export, ledger write, and read-back are an unconditional precondition of
    # termination. Re-read only after all three so a sibling's stamp landing
    # during that work invalidates the stale supersession before any destructive
    # route is entered. `None` is the held outcome; `supersession_held` records
    # why this pass declined to act.
    if supersession_held(orphan=orphan, inputs=inputs, dry_run=False):
        return None
    termination = terminate_orphan_run(
        port=port,
        run_id=orphan.run_id,
        status_kind=orphan.status_kind,
        destructive_action_held=lambda: supersession_held(
            orphan=orphan,
            inputs=inputs,
            dry_run=False,
        ),
    )
    if termination is None:
        return None
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
