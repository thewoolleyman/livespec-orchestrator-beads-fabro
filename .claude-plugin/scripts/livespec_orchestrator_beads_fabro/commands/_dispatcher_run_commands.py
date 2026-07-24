"""Dispatcher dispatch command handler."""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_mutex import (
    AdmissionMutexRefusal,
    claim_dispatch_admission_mutex,
    release_dispatch_admission_mutex,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
    alarm_on_terminal_failure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
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
    spans_path,
    store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict import (
    reflector_oob_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    dispatch_preamble,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    post_verdict_runner,
    self_update_after_verdict,
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
    target = _target_item(args=args, repo=repo, items=items)
    if target is None:
        return EXIT_PRECONDITION_ERROR
    outcome = _admit_and_dispatch_target(
        args=args,
        repo=repo,
        items=items,
        target=target,
        journal=journal,
        janitor=janitor,
    )
    if isinstance(outcome, int):
        return outcome
    emit_outcomes(outcomes=[outcome], as_json=args.as_json)
    # Verdict computed BEFORE the fail-open reflection + notification
    # stages; immutable by both (loop-reflection-gate best-practices §6 /
    # 0jxs operability gate). The alarm is strictly best-effort.
    exit_code = 0 if outcome.status == "green" else EXIT_FAILURE
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
    reflect(
        outcomes=[outcome],
        journal=journal,
        journal_path=journal_path(args=args, repo=repo),
        spans_path=spans_path(args=args, repo=repo),
    )
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _target_item(*, args: argparse.Namespace, repo: Path, items: list[WorkItem]) -> WorkItem | None:
    ready = ready_items(items=items, repo=repo)
    target = next((item for item in ready if item.id == args.item), None)
    if target is not None:
        return target
    all_ids = {item.id for item in items}
    if args.item not in all_ids:
        msg = (
            f"ERROR: work-item {args.item} not found in the target-tenant"
            f" ({repo.name}); --target-repo and --item must reference the same tenant\n"
        )
        _ = write_stderr(text=msg)
    else:
        _ = write_stderr(text=f"ERROR: work-item {args.item} is not in the ready set\n")
    return None


def _admit_and_dispatch_target(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    target: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome | int:
    # The interim host-wide admission mutex runs BEFORE the admission valve
    # mutates the Ledger or any Fabro sandbox work starts. It is deliberately
    # recorded as bd-ib-sd8o deliverable (c), to be removed or demoted by
    # deliverable (b).
    guard = claim_dispatch_admission_mutex(
        repo=repo, fabro_bin="fabro", runner=ShellCommandRunner()
    )
    if isinstance(guard, AdmissionMutexRefusal):
        _journal_mutex_refusal(journal=journal, refusal=guard)
        _ = write_stderr(text=guard.detail)
        return EXIT_PRECONDITION_ERROR
    try:
        # The admission valve runs BEFORE the Fabro launch: a host-only item is
        # routed away, a manual / unresolvable-assignee item is held + surfaced,
        # and an admission-eligible item is admitted (ready -> active, assignee
        # set) and dispatched. A targeted dispatch is an operator override, so it
        # does NOT enforce the per-repo WIP cap (the queue-draining `loop` does).
        admission = admit_and_select(
            repo=repo,
            items=items,
            candidates=[target],
            journal=journal,
            enforce_cap=False,
        )
        dispatched = [
            dispatch_one(args=args, repo=repo, item=item, journal=journal, janitor=janitor)
            for item in admission.admitted
        ]
        return (admission.refused + dispatched)[0]
    finally:
        release_dispatch_admission_mutex(claim=guard)


def _journal_mutex_refusal(*, journal: JournalFile, refusal: AdmissionMutexRefusal) -> None:
    journal.append(
        record={
            "stage": "dispatch-admission-mutex",
            "guard": "interim bd-ib-sd8o deliverable (c)",
            "run_id": refusal.run_id,
            "refused": True,
        }
    )
