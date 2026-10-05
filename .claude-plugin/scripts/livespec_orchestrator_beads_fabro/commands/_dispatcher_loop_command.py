"""Dispatcher loop command handler."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_projection_posture import (
    acp_projection_posture,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    pre_dispatch_criteria_refusal,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    credential_wrapper_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    proof_credentials_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    proof_assets_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    reclaim_stale_publish_branches,
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


def _pre_dispatch_wall_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    selected_candidates: Sequence[WorkItem],
    journal: JournalFile,
) -> int | None:
    """The drain's three pre-dispatch walls, as ONE decision: an exit code, or None.

    The same composition `_dispatcher_run_commands` uses for the single-dispatch
    path, and for the same two reasons. The three walls share one POSITION and one
    guarantee -- each runs after selection and BEFORE admission, so a refused
    candidate is never claimed and no factory run exists to reap -- and reading
    them as one gate keeps the drain's own return count honest, rather than
    suppressing a rule that exists to notice the entry point growing another exit.

    It sits after the `--dry-run` return deliberately: a dry run creates no run, so
    it stays a reporting surface that shows the operator exactly which candidate
    needs criteria.

    The criteria wall is first and is variant-aware (it exempts a groom-kind
    dispatch, whose acceptance is the human approval of the draft). The
    proof-ASSETS gate follows (S5 / bd-ib-b4u6b7): an item carrying a
    `factory_captured` assertion needs this repository's standing proof-assets
    prerelease before its capture stage can store an image. The proof-CREDENTIAL
    gate closes it (S8 / bd-ib-77vny7): an unusable `dispatcher.proof_credentials`
    declaration must refuse before a run exists, because the overlay each of these
    candidates is about to materialize would otherwise project it. That declaration
    is repository-level, so one refusal covers the whole wave, while the journal
    records are written per candidate.

    The publish-branch reclaim closes the wall and refuses NOTHING (bd-ib-yebrb7):
    a dead run's surviving publish branch is what makes a re-dispatch's
    `publish_draft` push non-fast-forward, and clearing it here -- once its head is
    preserved by reference -- is what lets the recovery publish and reach proof
    capture. It is per CANDIDATE, because a publish branch is per item, and it runs
    last because it MUTATES a remote ref: a wave this wall is about to refuse must
    leave the remote exactly as it found it.
    """
    ungradeable = pre_dispatch_criteria_refusal(
        items=selected_candidates, cwd=repo, workflow_name=args.workflow_name
    )
    if ungradeable is not None:
        _ = write_stderr(text=ungradeable)
        return EXIT_UNGRADEABLE_CRITERIA
    proof_refusal = proof_assets_refusal_for_items(
        runner=ShellCommandRunner(), repo=repo, items=selected_candidates, journal=journal
    )
    if proof_refusal is not None:
        _ = write_stderr(text=proof_refusal)
        return EXIT_PRECONDITION_ERROR
    credentials_refusal = proof_credentials_refusal_for_items(
        repo=repo,
        environ=os.environ,
        wrapper_text=credential_wrapper_text(repo=repo),
        work_item_ids=[item.id for item in selected_candidates],
        journal=journal,
    )
    if credentials_refusal is not None:
        _ = write_stderr(text=credentials_refusal)
        return EXIT_PRECONDITION_ERROR
    reclaim_stale_publish_branches(args=args, repo=repo, items=selected_candidates, journal=journal)
    return None


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
    wall_exit = _pre_dispatch_wall_exit(
        args=args, repo=repo, selected_candidates=selected_candidates, journal=journal
    )
    if wall_exit is not None:
        return wall_exit
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
    # BEFORE CLAIM, and before any candidate is selected: an unresolved ACP
    # projection-failure fact means a run's fallback evidence was never read,
    # so an UNATTENDED pass stops picking for this repository while an
    # ATTENDED `--item` pass proceeds once the high-urgency warning is
    # surfaced. Neither path clears the fact.
    posture = acp_projection_posture(
        journal_path=journal_path(args=args, repo=repo), attended=bool(requested_ids)
    )
    if posture.warning is not None:
        _ = write_stderr(text=posture.warning)
        journal.append(record=posture.journal_record())
    if posture.stop_picking:
        emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
    return _LoopStart(janitor=janitor, items=items, journal=journal)
