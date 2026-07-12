"""Dispatcher loop command handler."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
    autonomous_armed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous import (
    arm_autonomous_for_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
    alarm_on_terminal_failure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import ensure_otel_receiver
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
    requested_items_preflight_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    post_verdict_runner,
    self_update_after_verdict,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "run_loop_command",
]


def run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = ensure_otel_receiver(args=args, repo=repo)
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
    # Full autonomous mode two-factor arming: surface + journal the dangerous
    # acknowledgement when this run is armed (persistent permission + explicit
    # --mode autonomous). The armed bool is threaded onto `args` so the three
    # in-band consumers — the admission approve-gate collapse, the post-merge
    # acceptance collapse, and the post-run needs-human resolve-or-escalate
    # stage — read it and collapse/resolve to their autonomous leg; a non-armed
    # run is transparent (every gate keeps its normal policy).
    args.autonomous_armed = arm_autonomous_for_loop(
        mode=args.mode, repo=repo, journal=journal
    ).armed
    requested_ids = set(args.items or [])
    if requested_ids:
        preflight_error = requested_items_preflight_error(
            requested_ids=requested_ids, items=items, repo=repo
        )
        if preflight_error is not None:
            _ = write_stderr(text=preflight_error)
            return EXIT_PRECONDITION_ERROR
    selected_candidates = candidates(args=args, items=items, repo=repo)[: args.budget]
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
        armed=autonomous_armed(args=args),
    )
    journal.append(
        record={
            "stage": "loop-pick",
            "mode": args.mode,
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
    outcomes = admission.refused + dispatched
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
