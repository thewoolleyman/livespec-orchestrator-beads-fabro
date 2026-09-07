"""Dispatcher dispatch command handler."""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
    EXIT_UNGRADEABLE_CRITERIA,
    alarm_on_terminal_failure,
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    args_with_dispatch_factory_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    prepare,
    ready_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import arm_otel_egress
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    run_turn_sink_path,
    spans_path,
    store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict import (
    reflector_oob_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_readiness_diagnostics import (
    not_ready_requested_items_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import (
    ReworkPass,
    rework_redispatch_eligible_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    dispatch_preamble,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_guard import (
    append_run_turn_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import RunTurnSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    post_verdict_runner,
    self_update_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    args_with_dispatch_workflow_name,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "run_dispatch_command",
]


def run_dispatch_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    arm_otel_egress(args=args, repo=repo)
    prepared = prepare(args=args, repo=repo)
    if prepared is None:
        return EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return EXIT_FAILURE
    selected = _target_item(args=args, repo=repo, items=items, journal=journal)
    if selected is None:
        return EXIT_PRECONDITION_ERROR
    target, marked = selected
    # The pre-dispatch wall runs after selection and BEFORE admission, so a
    # refused item is never claimed and no factory run exists to reap. It is
    # handed this dispatch's explicit `--workflow-name` because the wall is
    # variant-aware: it resolves which graph the target would run and exempts a
    # groom-kind dispatch, whose acceptance is the human approval of the draft.
    ungradeable = pre_dispatch_criteria_refusal(
        items=[target], cwd=repo, workflow_name=args.workflow_name
    )
    if ungradeable is not None:
        _ = write_stderr(text=ungradeable)
        return EXIT_UNGRADEABLE_CRITERIA
    outcome = _admit_and_dispatch_target(
        args=args,
        repo=repo,
        items=items,
        target=target,
        journal=journal,
        janitor=janitor,
        marked=marked,
    )
    emit_outcomes(outcomes=[outcome], as_json=args.as_json)
    # Verdict computed BEFORE the fail-open reflection + notification
    # stages; immutable by both (loop-reflection-gate best-practices §6 /
    # 0jxs operability gate). The alarm is strictly best-effort.
    exit_code = dispatch_exit_code(outcomes=[outcome])
    alarm_on_terminal_failure(
        outcomes=[outcome],
        include_loop_summary=False,
        journal=journal,
    )
    cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=[outcome],
        journal=journal,
        runner=post_verdict_runner(runner=None),
    )
    self_update_after_verdict(
        repo=repo,
        outcomes=[outcome],
        journal=journal,
        runner=post_verdict_runner(runner=None),
    )
    dispatch_journal_path = journal_path(args=args, repo=repo)
    append_run_turn_checks(
        outcomes=(outcome,),
        journal=journal,
        journal_path=dispatch_journal_path,
        sink=RunTurnSink(path=run_turn_sink_path(args=args, repo=repo)),
    )
    reflect(
        outcomes=[outcome],
        journal=journal,
        journal_path=dispatch_journal_path,
        spans_path=spans_path(args=args, repo=repo),
    )
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _target_item(
    *, args: argparse.Namespace, repo: Path, items: list[WorkItem], journal: JournalFile
) -> tuple[WorkItem, bool] | None:
    """Resolve `--item` to its target plus whether it is a rework re-dispatch.

    The named item is eligible when it is `ready`, OR when the claim accounting
    classifies it as a marked, lock-less `active` row. The second arm is the
    ratified operator override: `--item` NARROWS the selection to one id and
    never bypasses it, so a marked row is reached THROUGH the same eligibility
    the drain applies — including the double-selection guard, since a marked
    row holding a live dispatch lock is not in that class and falls through to
    the already-claimed refusal below. Every OTHER non-`ready` item is still a
    precondition error.
    """
    ready = ready_items(items=items, repo=repo)
    target = next((item for item in ready if item.id == args.item), None)
    if target is not None:
        return target, False
    marked_ids = rework_redispatch_eligible_ids(repo=repo, items=items, journal=journal)
    if args.item in marked_ids:
        return next(item for item in items if item.id == args.item), True
    all_ids = {item.id for item in items}
    if args.item not in all_ids:
        msg = (
            f"ERROR: work-item {args.item} not found in the target-tenant"
            f" ({repo.name}); --target-repo and --item must reference the same tenant\n"
        )
        _ = write_stderr(text=msg)
    else:
        _ = write_stderr(
            text=not_ready_requested_items_error(
                requested_ids={args.item},
                items=items,
                repo=repo,
            )
        )
    return None


def _admit_and_dispatch_target(  # noqa: PLR0913 — kw-only targeted dispatch; `marked` is the leg the target rides, decided at selection.
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    target: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    marked: bool,
) -> DispatchOutcome:
    # The admission valve runs BEFORE the Fabro launch: a host-only item is
    # routed away, a manual / unresolvable-assignee item is held + surfaced,
    # and an admission-eligible item is admitted (ready -> active, assignee
    # set) and dispatched. A targeted dispatch is an operator override, so it
    # does NOT enforce the per-repo WIP cap (the queue-draining `loop` does) —
    # for a marked target on the same terms as a ready one, since the override
    # narrows WHICH item runs rather than granting rework its own bypass. A
    # marked target rides the rework leg alone: it is already `active`, so
    # offering it to the ready plan as well would re-admit and re-launch the
    # same row twice in one pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=[] if marked else [target],
        journal=journal,
        enforce_cap=False,
        rework=ReworkPass(scope_ids=frozenset({target.id})),
    )
    dispatched = [
        dispatch_one(
            # Both per-dispatch ledger pins, as in the queue-draining loop:
            # the factory this dispatch goes to and the workflow variant it
            # runs are recorded on the item together.
            args=args_with_dispatch_workflow_name(
                args=args_with_dispatch_factory_target(args=args, repo=repo, work_item_id=item.id),
                repo=repo,
                work_item_id=item.id,
            ),
            repo=repo,
            item=item,
            journal=journal,
            janitor=janitor,
        )
        for item in (*admission.rework, *admission.admitted)
    ]
    return (admission.refused + dispatched)[0]
