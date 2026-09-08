"""Dispatcher loop command handler."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe import (
    await_usable_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_dry_run import dry_run_outcomes
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    candidates,
    prepare,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_wave import (
    dispatch_loop_wave,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    dispatch_preamble,
    requested_items_preflight_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_guard import (
    append_run_turn_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import RunTurnSink
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
    # `--item` narrows BOTH legs to the named ids, and `--budget` bounds the
    # pass as a whole rather than each leg separately.
    rework = ReworkPass(
        scope_ids=frozenset(args.items) if args.items else None,
        budget=args.budget,
    )
    if args.dry_run:
        picked = dry_run_outcomes(
            repo=repo,
            items=items,
            journal=journal,
            selected_candidates=selected_candidates,
            rework=rework,
        )
        # The journal record and the reported outcome list are projected from
        # the SAME `picked` value, so the audit record and the "what would this
        # drain do?" surface can never disagree.
        journal.append(
            record={
                "stage": "loop-pick",
                "dry_run": True,
                "budget": args.budget,
                "picked": [outcome.work_item_id for outcome in picked],
            }
        )
        emit_outcomes(outcomes=picked, as_json=args.as_json)
        return 0
    # The pre-dispatch wall guards the DRAIN too, and it sits after the dry-run
    # return deliberately: `--dry-run` creates no run, so it stays a reporting
    # surface that shows the operator exactly which candidate needs criteria.
    ungradeable = pre_dispatch_criteria_refusal(
        items=selected_candidates, cwd=repo, workflow_name=args.workflow_name
    )
    if ungradeable is not None:
        _ = write_stderr(text=ungradeable)
        return EXIT_UNGRADEABLE_CRITERIA
    # A provider-limit credential refusal HOLDS this pass open instead of
    # ending it, re-probing on the committed cadence until the probe itself
    # reports usable. Placed here for two reasons a later reader would
    # otherwise have to reconstruct: it sits AFTER the dry-run return, because
    # a dry run launches nothing and so has no credential to wait on; and it
    # runs only when this pass actually holds candidates, because an empty pass
    # has no admission to resume and must not block on a credential it will
    # never spend. The result is deliberately discarded — admission proceeds
    # either way, and every refusal re-probing cannot fix stays the
    # per-dispatch refusal's business.
    if selected_candidates:
        _ = await_usable_credential(repo=repo, journal=journal, budget=args.budget)
    outcomes = dispatch_loop_wave(
        args=args,
        repo=repo,
        items=items,
        selected_candidates=selected_candidates,
        journal=journal,
        janitor=janitor,
        rework=rework,
    )
    if not outcomes:
        emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
    emit_outcomes(outcomes=outcomes, as_json=args.as_json)
    # Verdict is computed BEFORE the mechanical reflection stage and is
    # immutable by it (loop-reflection-gate best-practices §6: reflection
    # never changes a dispatch verdict). reflect() is fail-open and never
    # raises — it cannot alter `exit_code`.
    exit_code = dispatch_exit_code(outcomes=outcomes)
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
    dispatch_journal_path = journal_path(args=args, repo=repo)
    append_run_turn_checks(
        outcomes=tuple(outcomes),
        journal=journal,
        journal_path=dispatch_journal_path,
        sink=RunTurnSink(path=run_turn_sink_path(args=args, repo=repo)),
    )
    reflect(
        outcomes=outcomes,
        journal=journal,
        journal_path=dispatch_journal_path,
        spans_path=spans_path(args=args, repo=repo),
    )
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


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
            requested_ids=requested_ids, items=items, repo=repo, journal=journal
        )
        if preflight_error is not None:
            _ = write_stderr(text=preflight_error)
            return EXIT_PRECONDITION_ERROR
    return _LoopStart(janitor=janitor, items=items, journal=journal)
