"""Completing a handed-off merge wait from the stranded-claim reconciliation pass.

A merge wait that handed its pull request off left the item `active` under its
claim (`_dispatcher_merge_wait_handoff`), and this is the pass that finishes it
from whatever the forge now reports. The reading is
`_dispatcher_stranded_claim_handoff`; the three routes it can earn are:

- MERGED: perform `reconcile-merged` for the item in the same pass, with no
  `resolve-blocked` and no `resume`. The valve is driven through its own command
  function, as the host-record primitive drives it, so there is one acceptance
  re-run path and not two that could diverge.
- A REQUIRED CHECK FAILED: record exactly the outcome the merge wait's terminal
  required-check failure records, through the SAME builder, and apply it through
  the terminal-completion route's own disposition.
- THE PULL REQUEST WILL NOT MERGE (closed unmerged, or auto-merge no longer
  armed): rest the item at `blocked / needs-human` with the cause
  `merge-poll-budget-exhausted`, exactly as the merge wait's own rest does.

THE FENCE IS TAKEN FIRST AND THE VALVE IS DRIVEN WITH `force`, for one reason that
is easy to miss. The fence IS the primary checkout's dispatch lock, and the valve's
preflight refuses an item whose dispatch lock is held by a live process unless
`force` is set; this pass holds that lock itself, and has already established that
no OTHER live owner exists (the ladder's `dispatch-live` hold precedes the route).
So `force` here does not override a live dispatch, it steps past this pass's own
lock.

THIS PASS DOES NOT RE-RUN A FAILED CHECK, and it MUST NOT: the merge wait judges
one attempt of a required check, and the failed-check recovery owns any automatic
re-run, counted from the journal, at most once per head. What is recorded here is
the outcome of the attempt the forge currently reports.

EVERY LEDGER READ THAT FAILS HOLDS THE CLAIM, and a disposition the claim-token
protocol refused is a hold too, under the reasons the sibling routes use.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record import (
    record_base_advanced_after_arming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_exhaustion import (
    exhausted_rest_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import FALLBACK_SOURCE
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_checks import (
    required_check_failure_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects import (
    claim_row,
    claim_unchanged,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_fence import (
    claim_recovery_fence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ACTION_HANDOFF_RECONCILE_MERGED,
    ACTION_HANDOFF_REQUIRED_CHECK_FAILED,
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
    HOLD_RUN_SUCCEEDED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff import (
    HANDED_OFF_HOLD_DETAIL,
    HandoffReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    STRANDED_CLAIM_HANDOFF_STAGE,
    HeldClaim,
    RecoveredClaim,
    recovery_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_terminal import (
    RefusedDisposition,
    TerminalObservation,
    apply_terminal_disposition,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "HandoffRecoveryRequest",
    "reconcile_merged_for_claim",
    "recover_handed_off_claim",
]

_ACTIVE_STATUS = "active"
_REASON_RECONCILED = "merged"
_REASON_REQUIRED_CHECK_FAILED = "required-check-failed"
_REASON_NOT_MERGEABLE = "pull-request-will-not-merge"


@dataclass(frozen=True, kw_only=True)
class HandoffRecoveryRequest:
    """One graded handed-off claim, with the reading its route was chosen on."""

    item: WorkItem
    run_id: str
    factory_name: str
    factory_server_url: str | None
    action: str
    reading: HandoffReading


def reconcile_merged_for_claim(*, args: argparse.Namespace) -> int:
    """Drive the reconcile valve, imported here for the cycle reason the host-record CLI records."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged import (
        run_reconcile_merged_command,
    )

    return run_reconcile_merged_command(args=args)


def recover_handed_off_claim(
    *,
    repo: Path,
    journal: JournalFile,
    request: HandoffRecoveryRequest,
    now_iso: str,
) -> RecoveredClaim | HeldClaim:
    """Complete this handed-off claim under the primary checkout's lock."""
    with claim_recovery_fence(
        repo=repo, work_item_id=request.item.id, run_id=request.run_id
    ) as fenced:
        if not fenced:
            return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
        row = claim_row(repo=repo, work_item_id=request.item.id)
        if row is None:
            return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
        if not claim_unchanged(row=row, run_id=request.run_id):
            return _held(request=request, reason=HOLD_CLAIM_CHANGED)
        journal.append(
            record=recovery_journal_record(
                stage=STRANDED_CLAIM_HANDOFF_STAGE,
                recovered=_recovered(
                    request=request, status=row.status or _ACTIVE_STATUS, effects=()
                ),
            )
        )
        if request.action == ACTION_HANDOFF_RECONCILE_MERGED:
            return _reconcile(repo=repo, journal=journal, request=request)
        return _rest(repo=repo, journal=journal, request=request, now_iso=now_iso)


def _reconcile(
    *, repo: Path, journal: JournalFile, request: HandoffRecoveryRequest
) -> RecoveredClaim | HeldClaim:
    """Perform `reconcile-merged`; a refusal holds the claim naming the exit code."""
    identity = journal.identity
    exit_code = reconcile_merged_for_claim(
        args=argparse.Namespace(
            repo=str(repo),
            item=request.item.id,
            janitor=None,
            journal=str(journal.path),
            invoker=None if identity.invoker_source == FALLBACK_SOURCE else identity.invoker,
            force=True,
            regrade=False,
            handed_off_rework=request.item.rework_pending,
            as_json=False,
        )
    )
    if exit_code != 0:
        return _held(
            request=request,
            reason=HOLD_RUN_SUCCEEDED,
            detail=(
                f"{HANDED_OFF_HOLD_DETAIL}: pull request #{request.reading.pr_number} merged but "
                f"reconcile-merged did not complete (exit {exit_code}); read its stderr"
            ),
        )
    row = claim_row(repo=repo, work_item_id=request.item.id)
    return _recovered(
        request=request,
        status=_ACTIVE_STATUS if row is None else row.status or _ACTIVE_STATUS,
        effects=("reconcile-merged",),
    )


def _rest(
    *, repo: Path, journal: JournalFile, request: HandoffRecoveryRequest, now_iso: str
) -> RecoveredClaim | HeldClaim:
    """Record the ending a failed check or an unmergeable pull request earns."""
    outcome = replace(_outcome(request=request), fabro_run_id=request.run_id)
    if request.action != ACTION_HANDOFF_REQUIRED_CHECK_FAILED:
        record_base_advanced_after_arming(
            repo=repo, item=request.item, outcome=outcome, journal=journal
        )
    applied = apply_terminal_disposition(
        repo=repo,
        item=request.item,
        observation=TerminalObservation(outcome=outcome),
        journal=journal,
        now_iso=now_iso,
    )
    if isinstance(applied, RefusedDisposition):
        lost = applied.outcome == HOLD_CLAIM_CHANGED
        return _held(
            request=request,
            reason=HOLD_CLAIM_CHANGED if lost else HOLD_EFFECT_UNOBSERVABLE,
        )
    return _recovered(request=request, status="blocked", effects=applied)


def _outcome(*, request: HandoffRecoveryRequest) -> DispatchOutcome:
    reading = request.reading
    if request.action == ACTION_HANDOFF_REQUIRED_CHECK_FAILED:
        return required_check_failure_outcome(
            outcome_type=DispatchOutcome,
            plan=reading.plan,
            number=reading.pr_number,
            merge_sha=reading.merge_sha,
            failed=list(reading.failed_checks),
        )
    return exhausted_rest_outcome(
        outcome_type=DispatchOutcome,
        plan=reading.plan,
        number=reading.pr_number,
        pr_head=reading.pr_head,
        default_branch_tip=reading.pr_base,
        run_id=request.run_id,
    )


def _recovered(
    *, request: HandoffRecoveryRequest, status: str, effects: tuple[str, ...]
) -> RecoveredClaim:
    return RecoveredClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        reason={
            ACTION_HANDOFF_RECONCILE_MERGED: _REASON_RECONCILED,
            ACTION_HANDOFF_REQUIRED_CHECK_FAILED: _REASON_REQUIRED_CHECK_FAILED,
        }.get(request.action, _REASON_NOT_MERGEABLE),
        route=request.action,
        status=status,
        effects_written=effects,
    )


def _held(*, request: HandoffRecoveryRequest, reason: str, detail: str | None = None) -> HeldClaim:
    return HeldClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        dispatching_host=None,
        hold_reason=reason,
        remedy=None,
        detail=detail,
    )
