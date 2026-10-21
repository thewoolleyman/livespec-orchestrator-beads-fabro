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

A `superseded-run` reading is RE-CONFIRMED before export and again at the
termination boundary (`_dispatcher_reconcile_supersession.py`). It is the one
orphan reason whose evidence is the journal snapshot this pass opened with,
and another session's launch stamp landing between that read and the inventory
read leaves the pass about to cancel the item's NEWEST run. A reading either
fresh read does not reproduce is held rather than acted on.

RECONCILING A RUN ALSO RECLAIMS ITS SANDBOX CONTAINER, which is a lane of its
own rather than a step of the orphan path: the orphan join considers only
non-terminal runs, while a leaked container belongs to a run that has already
ENDED (`_dispatcher_sandbox_container_sweep.py`). Those containers keep
running inside the FACTORY HOST's `fabro-sandbox.slice` and keep spending the
memory and CPU envelope the live runs share, so the leak raises OOM and
throttle risk for real work as runs fail. The sweep addresses each surveyed
factory's own Docker daemon rather than the reconciling host's
(`_dispatcher_reconcile_runs_containers.py`), it grades every container
against the inventory this pass already read — it takes no second reading,
because two readings a moment apart disagree about a run that terminated
between them — and it fails closed in every direction it can be blinded.

A run parked at a human gate whose item is still live has no moot question to
release it, so it is governed instead by `dispatcher.blocked_run_grace_seconds`
(`_dispatcher_reconcile_runs_grace.py`). Past the grace it becomes an orphan
like any other and takes the same export-then-terminate path; inside it — or
with a park nobody can measure — it is REPORTED as held and left running. The
held set is carried separately from the reconciled set precisely so that
"reported" can never become "terminated" by a later edit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_one_run import (
    reconcile_one_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_containers import (
    pass_container_sweeps,
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
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_supersession import (
    supersession_held,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    ClaimLaneResult,
)

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


@dataclass(frozen=True, kw_only=True)
class _FactoryPass:
    """What one factory's survey produced beside the orphans it reconciled.

    `run_statuses` is that factory's whole inventory — terminal runs
    included — because the container sweep's question is about runs the
    orphan join deliberately ignores. It is carried back rather than
    accumulated through a parameter so `_reconcile_one_factory` keeps the
    argument count its own refusal arms need.

    `surveyed` is NOT `bool(run_statuses)`: a factory that answered with an
    empty inventory was surveyed, and its answer is what makes a container on
    that factory's host an ungradeable leak worth reporting. A factory that
    could not be reached, or that declares no server, was not — and the
    container lane never addresses an unsurveyed factory's daemon, because a
    survey that could not be taken cannot license a removal.
    """

    held: tuple[HeldRun, ...]
    run_statuses: Mapping[str, str | None]
    surveyed: bool


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
    run_statuses: dict[str, str | None] = {}
    # The surveyed factories themselves rather than a bool: the container lane
    # addresses each factory's OWN Docker daemon, so it needs to know WHICH
    # factories answered, not merely that one did.
    surveyed: list[FactoryTarget] = []
    # Keyed BY FACTORY rather than merged into `run_statuses` above: the claim
    # lane grades each claim against the listing of the factory its stamp
    # names, and a factory absent from this mapping is one this pass did not
    # survey — which is what holds its claims as `factory-unobservable` rather
    # than grading them against an inventory nobody took.
    observed: dict[str, Mapping[str, str | None]] = {}
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
        surveyed_factory = _reconcile_one_factory(
            inputs=inputs,
            factory=factory,
            item_statuses=item_statuses,
            dry_run=dry_run,
            reconciled=reconciled,
            errors=errors,
        )
        held.extend(surveyed_factory.held)
        run_statuses.update(surveyed_factory.run_statuses)
        if surveyed_factory.surveyed:
            observed[factory.name] = surveyed_factory.run_statuses
            surveyed.append(factory)
    if not dry_run:
        for error in errors:
            journal_error(journal=inputs.journal, error=error)
    claims = _claim_lane(
        inputs=inputs, factories=tuple(factories), observed=observed, dry_run=dry_run
    )
    return ReconcileRunsSummary(
        reconciled=tuple(reconciled),
        errors=tuple(errors),
        dry_run=dry_run,
        held=tuple(held),
        containers=pass_container_sweeps(
            inputs=inputs,
            factories=tuple(surveyed),
            run_statuses=run_statuses,
            dry_run=dry_run,
        ),
        recovered_claims=claims.recovered,
        held_claims=claims.held,
    )


def _claim_lane(
    *,
    inputs: ReconcileInputs,
    factories: tuple[FactoryTarget, ...],
    observed: Mapping[str, Mapping[str, str | None]],
    dry_run: bool,
) -> ClaimLaneResult:
    """Run the injected CLAIM lane, or report that no pass supplied one.

    Injected rather than imported: the lane's terminal-completion route reaches
    the Dispatcher's own terminal dispositions, one of which reaches this module
    back, so importing it here would close a runtime cycle. The two
    reconciliation surfaces supply it; the narrow observation-only callers do
    not, and get the empty result.
    """
    lane = inputs.claim_lane
    if lane is None:
        return ClaimLaneResult()
    return lane(inputs=inputs, factories=factories, observed=observed, dry_run=dry_run)


def _reconcile_one_factory(
    *,
    inputs: ReconcileInputs,
    factory: FactoryTarget,
    item_statuses: dict[str, str],
    dry_run: bool,
    reconciled: list[ReconciledRun],
    errors: list[ReconcileError],
) -> _FactoryPass:
    """Reconcile one factory's orphans, reporting its holds and its inventory."""
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
        # No statuses, so every container this factory owns reads as a run
        # nobody reported and the sweep holds it. A survey that could not be
        # taken must not license a removal.
        return _FactoryPass(held=(), run_statuses={}, surveyed=False)
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
    # NO EVENT-PROJECTION REPLAY RIDES THIS SURVEY. The replay that stood here
    # re-read each unresolved projection-failure fact's run through
    # `fabro events`; v127 retired both the fact and the projection, so there
    # is nothing left to replay and nothing a replay could learn. What v127
    # SEPARATELY requires -- replaying selection-to-execution observation
    # idempotently, keyed by factory, run, node attempt and selection identity
    # -- is NOT discharged here, and nothing this survey calls performs it. The
    # orphan disposal below names no selection, fallback or release at all, and
    # the provider-limit release leg is reached only from
    # `_dispatcher_terminal_routing`, on the DISPATCH terminal path this survey
    # never enters. Re-sourcing that replay from the authoritative
    # `acp-node-selection` and `provider-limit-release` records is the
    # follow-on item `bd-ib-augqc2`, the other half of the same v127 proposal.
    # Do NOT read this deletion as evidence the obligation is met.
    for orphan in classify_orphans(inventory=inventory, grace=grace):
        if inputs.only_work_item_id is not None and orphan.work_item_id != inputs.only_work_item_id:
            continue
        # This first re-read cheaply holds a race already visible before export.
        # `_reconcile_one_run` repeats it at the termination boundary because a
        # sibling dispatch can stamp this run while the export is in flight.
        if supersession_held(orphan=orphan, inputs=inputs, dry_run=dry_run):
            continue
        outcome = reconcile_one_run(inputs=inputs, port=port, orphan=orphan, dry_run=dry_run)
        if outcome is None:
            continue
        if isinstance(outcome, ReconcileError):
            errors.append(outcome)
            continue
        reconciled.append(outcome)
    return _FactoryPass(
        held=classify_blocked_holds(inventory=inventory, grace=grace),
        run_statuses={run.run_id: run.status_kind for run in ps.runs},
        surveyed=True,
    )
