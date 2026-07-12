"""Dispatcher dispatch/loop command handlers."""

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    candidates,
    prepare,
    ready_items,
    run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyPoster,
    notify_terminal,
    terminal_events,
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
    "run_dispatch_command",
    "run_loop_command",
]

_EXIT_FAILURE = 1
_EXIT_PRECONDITION_ERROR = 3


def run_dispatch_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = ensure_otel_receiver(args=args, repo=repo)
    prepared = prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return _EXIT_FAILURE
    ready = ready_items(items=items, repo=repo)
    target = next((item for item in ready if item.id == args.item), None)
    if target is None:
        all_ids = {item.id for item in items}
        if args.item not in all_ids:
            msg = (
                f"ERROR: work-item {args.item} not found in the target-tenant"
                f" ({repo.name}); --target-repo and --item must reference the same tenant\n"
            )
            _ = write_stderr(text=msg)
        else:
            _ = write_stderr(text=f"ERROR: work-item {args.item} is not in the ready set\n")
        return _EXIT_PRECONDITION_ERROR
    # The admission valve runs BEFORE the Fabro launch: a host-only item is
    # routed away, a manual / unresolvable-assignee item is held + surfaced,
    # and an admission-eligible item is admitted (ready -> active, assignee
    # set) and dispatched. A targeted dispatch is an operator override, so it
    # does NOT enforce the per-repo WIP cap (the queue-draining `loop` does).
    # The targeted `dispatch --item` path NEVER arms full autonomous mode — the
    # `--mode autonomous` opt-in rides the queue-draining `loop`, not `dispatch`
    # (SPECIFICATION/contracts.md) — so the admission valve runs with the mode
    # collapse OFF (armed=False), exactly the pre-mode behavior.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=[target],
        journal=journal,
        enforce_cap=False,
        armed=False,
    )
    dispatched = [
        dispatch_one(args=args, repo=repo, item=item, journal=journal, janitor=janitor)
        for item in admission.admitted
    ]
    outcome = (admission.refused + dispatched)[0]
    emit_outcomes(outcomes=[outcome], as_json=args.as_json)
    # Verdict computed BEFORE the fail-open reflection + notification
    # stages; immutable by both (loop-reflection-gate best-practices §6 /
    # 0jxs operability gate). The alarm is strictly best-effort.
    exit_code = 0 if outcome.status == "green" else _EXIT_FAILURE
    _alarm_on_terminal_failure(
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


def run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = ensure_otel_receiver(args=args, repo=repo)
    prepared = prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return _EXIT_FAILURE
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
            return _EXIT_PRECONDITION_ERROR
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
    exit_code = 0 if all(outcome.status == "green" for outcome in outcomes) else _EXIT_FAILURE
    _alarm_on_terminal_failure(
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


def _alarm_on_terminal_failure(
    *,
    outcomes: list[DispatchOutcome],
    include_loop_summary: bool,
    journal: JournalFile,
    poster: NotifyPoster | None = None,
) -> None:
    """Fire the fail-open ntfy alarm for any terminal failure (0jxs gate).

    Called AFTER the verdict / exit code is computed, so it can never
    change it. Derives the leak-free alarm events (one per non-green
    outcome — `failed`/`blocked`, covering uvd's `host-only-refused` —
    plus a `non-green-loop` summary for the loop command), then posts them
    fail-open: a missing topic, an unreachable server, or any POST error
    is journaled and swallowed, never raised. A fully-green wave fires
    nothing. `poster` is injectable for the hermetic test tier; production
    is the real `HttpNotifyPoster`.
    """
    events = terminal_events(
        outcomes=tuple(outcomes),
        include_loop_summary=include_loop_summary,
    )
    notify_terminal(
        events=events,
        run_id=run_id(),
        poster=poster if poster is not None else HttpNotifyPoster(),
        journal=journal,
    )
