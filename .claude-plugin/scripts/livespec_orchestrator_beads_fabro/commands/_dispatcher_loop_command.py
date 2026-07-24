"""Dispatcher loop command handler."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
    candidates,
    prepare,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import arm_otel_egress
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    spans_path,
    store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_host_dispatch_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict import (
    reflector_oob_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    dispatch_preamble,
    requested_items_preflight_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    post_verdict_runner,
    self_update_after_verdict,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "run_loop_command",
]


@dataclass(frozen=True, kw_only=True)
class _LoopStart:
    janitor: tuple[str, ...] | None
    items: list[WorkItem]
    journal: JournalFile


def run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    started = _start_loop(args=args, repo=repo)
    if isinstance(started, int):
        return started
    janitor = started.janitor
    items = started.items
    journal = started.journal
    selected_candidates = candidates(args=args, items=items, repo=repo)[: args.budget]
    if args.dry_run:
        journal.append(
            record={
                "stage": "loop-pick",
                "dry_run": True,
                "budget": args.budget,
                "picked": [item.id for item in selected_candidates],
            }
        )
        emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
    outcomes = _dispatch_loop_wave(
        args=args,
        repo=repo,
        items=items,
        selected_candidates=selected_candidates,
        journal=journal,
        janitor=janitor,
    )
    if isinstance(outcomes, int):
        return outcomes
    if not outcomes:
        emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
    emit_outcomes(outcomes=outcomes, as_json=args.as_json)
    # Verdict is computed BEFORE the mechanical reflection stage and is
    # immutable by it (loop-reflection-gate best-practices §6: reflection
    # never changes a dispatch verdict). reflect() is fail-open and never
    # raises — it cannot alter `exit_code`.
    exit_code = 0 if all(outcome.status == "green" for outcome in outcomes) else EXIT_FAILURE
    alarm_on_terminal_failure(
        outcomes=outcomes,
        include_loop_summary=True,
        journal=journal,
    )
    cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=outcomes,
        journal=journal,
        runner=post_verdict_runner(runner=None),
    )
    self_update_after_verdict(
        repo=repo,
        outcomes=outcomes,
        journal=journal,
        runner=post_verdict_runner(runner=None),
    )
    reflect(
        outcomes=outcomes,
        journal=journal,
        journal_path=journal_path(args=args, repo=repo),
        spans_path=spans_path(args=args, repo=repo),
    )
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _dispatch_loop_wave(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    selected_candidates: list[WorkItem],
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> list[DispatchOutcome] | int:
    # The host-level dispatch admission cap (spec v047, contracts.md) runs
    # BEFORE the admission valve mutates the Ledger or any Fabro sandbox work
    # starts — the bd-ib-sd8o deliverable (b) counting demotion of the interim
    # binary mutex.
    guard = claim_dispatch_admission_mutex(
        repo=repo,
        fabro_bin="fabro",
        runner=ShellCommandRunner(),
        cap=resolve_host_dispatch_cap(cwd=repo),
    )
    if isinstance(guard, AdmissionMutexRefusal):
        _journal_mutex_refusal(journal=journal, refusal=guard)
        _ = write_stderr(text=guard.detail)
        return EXIT_PRECONDITION_ERROR
    try:
        return _admit_and_dispatch_loop_wave(
            args=args,
            repo=repo,
            items=items,
            selected_candidates=selected_candidates,
            journal=journal,
            janitor=janitor,
        )
    finally:
        release_dispatch_admission_mutex(claim=guard)


def _admit_and_dispatch_loop_wave(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    selected_candidates: list[WorkItem],
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> list[DispatchOutcome]:
    # The admission valve drains the candidate set up to the per-repo WIP cap:
    # host-only items are routed away, manual / unresolvable items are held +
    # surfaced, and the highest-rank admission-eligible items fill the free
    # slots (ready -> active, assignee set). Capacity-deferred items simply
    # wait for the next pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=selected_candidates,
        journal=journal,
        enforce_cap=True,
    )
    journal.append(
        record={
            "stage": "loop-pick",
            "dry_run": False,
            "budget": args.budget,
            "picked": [item.id for item in admission.admitted],
        }
    )
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [
            pool.submit(
                dispatch_one,
                args=args,
                repo=repo,
                item=item,
                journal=journal,
                janitor=janitor,
            )
            for item in admission.admitted
        ]
        dispatched = [future.result() for future in futures]
    # Held / host-only-refused items ride in the outcomes (so the verdict and
    # the post-verdict alarm see them); capacity-deferred items do not.
    return admission.refused + dispatched


def _journal_mutex_refusal(*, journal: JournalFile, refusal: AdmissionMutexRefusal) -> None:
    journal.append(
        record={
            "stage": "dispatch-admission-mutex",
            "guard": "host_dispatch_cap counting cap (bd-ib-sd8o deliverable (b))",
            "run_id": refusal.run_id,
            "refused": True,
        }
    )


def _start_loop(*, args: argparse.Namespace, repo: Path) -> _LoopStart | int:
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
    requested_ids = set(args.items or [])
    if requested_ids:
        preflight_error = requested_items_preflight_error(
            requested_ids=requested_ids, items=items, repo=repo
        )
        if preflight_error is not None:
            _ = write_stderr(text=preflight_error)
            return EXIT_PRECONDITION_ERROR
    return _LoopStart(janitor=janitor, items=items, journal=journal)
