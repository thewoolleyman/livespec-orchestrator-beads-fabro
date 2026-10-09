"""Operator valve for reconciling already-merged active or parked items.

The merged-PR RESOLUTION half lives in `_dispatcher_reconcile_merged_pr` and is
re-exported here, so this module stays the command supervisor — the journal, the
arm selection, and the shared outcome tail — and its published surface is
unchanged. The PREFLIGHT half lives in `_dispatcher_reconcile_preflight` for the
same reason: admitting an invocation and performing one are different concerns,
and it owns the whole status vocabulary rather than leaving a copy here.

THERE ARE THREE ARMS, and each is a sibling of the others rather than a branch
inside one, because each answers a different question with different evidence:

- the ORDINARY arm resolves the merge, re-runs the post-merge janitor, and
  accepts — the recovery for a dispatch that died after its pull request merged;
- the RE-ACCEPT arm, for an item already resting in `acceptance`, re-runs ONLY
  the acceptance pass against the records now on the pull request, because the
  janitor already ran and the clause forbids running it again;
- the `--regrade` arm lives in `_dispatcher_reconcile_regrade` and asks whether a
  criteria repair has made an already-merged item gradeable.

All three end at the one outcome tail below, which is what keeps the journal
record, the emitted payload and the exit code identical between them.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as selfup
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_result import (
    ACCEPTANCE_STAGE,
    outcome_after_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    complete_and_accept,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    invoker_from_args,
    require_invoker_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_output_retention import (
    janitor_retention,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import emit_outcomes
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    livespec_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
    janitor_reconcile_checkout_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged_pr import (
    merged_pr_list_argv,
    parse_merged_pr_list,
    resolve_merged_pr,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_preflight import (
    ACCEPTANCE_STATUS,
    reconcile_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_regrade import run_regrade
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "merged_pr_list_argv",
    "parse_merged_pr_list",
    "reconcile_plan",
    "run_reconcile_merged_command",
]

_UNMERGED_REFUSAL = "ERROR: no merged PR found for work-item {item_id}\n"


def run_reconcile_merged_command(
    *, args: argparse.Namespace, runner: CommandRunner | None = None
) -> int:
    """Run the reconcile valve for a stranded merged item, on its selected arm.

    Without `--regrade` that is the post-merge janitor plus the acceptance
    path; with it, the re-grade of an already-merged `rework:pending` item
    against its repaired criteria. Both arms share this function's preflight,
    journal and outcome tail, so the two differ in what they DO and never in
    how they report it.
    """
    repo = Path(args.repo)
    # FIRST, ahead of the tenant read and of every write: an unattributed
    # invocation under `dispatcher.require_invoker` is refused here so the
    # refusal itself performs no half of the reconcile.
    invoker_refusal = require_invoker_refusal(args=args, repo=repo)
    if invoker_refusal is not None:
        _ = write_stderr(text=invoker_refusal)
        return EXIT_PRECONDITION_ERROR
    preflight = reconcile_preflight(args=args, repo=repo)
    if isinstance(preflight, int):
        return preflight
    item = preflight.item
    janitor = preflight.janitor
    command_runner = ShellCommandRunner() if runner is None else runner
    journal = JournalFile(
        path=journal_path(args=args, repo=repo),
        identity=invoker_from_args(args=args),
    )
    # This valve's OWN identity, minted and journaled before the arms run. It
    # keys the post-merge janitor's retained-output artifacts, so a reader
    # holding a retained path can tie it back to the invocation that wrote it;
    # the dispatch path keys those on its dispatch id, and before this record
    # existed the valve had no identifier of its own to key them on at all.
    invocation = selfup.run_id()
    journal.append(
        record={
            "stage": "reconcile-merged-invocation",
            "work_item_id": item.id,
            "invocation_id": invocation,
        }
    )
    plan = replace(
        reconcile_plan(repo=repo, item=item, janitor=janitor, runner=command_runner),
        janitor_retention=janitor_retention(directory=journal.path.parent, invocation=invocation),
    )
    # The three arms, most specific first. `--regrade` is selected by the FLAG, so
    # it outranks the item's status; an item resting in `acceptance` then takes the
    # re-accept arm, because its merge and its janitor already ran and the clause
    # forbids running either again.
    if args.regrade:
        outcome = run_regrade(
            repo=repo, item=item, plan=plan, runner=command_runner, journal=journal
        )
    elif item.status == ACCEPTANCE_STATUS:
        outcome = _reaccept_in_acceptance(
            repo=repo, item=item, plan=plan, runner=command_runner, journal=journal
        )
    else:
        outcome = _janitor_and_accept(
            repo=repo, item=item, plan=plan, runner=command_runner, journal=journal
        )
    if isinstance(outcome, int):
        return outcome
    journal.append(record={"stage": "outcome", "outcome": _outcome_payload(outcome=outcome)})
    emit_outcomes(outcomes=[outcome], as_json=args.as_json)
    return 0 if _reconciled_green(outcome=outcome) else EXIT_FAILURE


def _resolved_merge(
    *, item: WorkItem, plan: DispatchPlan, runner: CommandRunner, journal: JournalFile
) -> PrView | int:
    """The merge both non-regrade arms key on, or the exit code that refuses.

    Shared rather than repeated per arm because the two arms differ in what they
    DO with the merge, never in which merge belongs to the item: two resolutions
    could come to name two different pull requests, and the disagreement would be
    invisible because each would be a plausible merge.
    """
    merged = resolve_merged_pr(plan=plan, item=item, runner=runner, journal=journal)
    if isinstance(merged, str):
        _ = write_stderr(text=merged)
        return EXIT_PRECONDITION_ERROR
    if merged is None:
        _ = write_stderr(text=_UNMERGED_REFUSAL.format(item_id=item.id))
        return EXIT_PRECONDITION_ERROR
    return merged


def _janitor_and_accept(
    *,
    repo: Path,
    item: WorkItem,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalFile,
) -> DispatchOutcome | int:
    """The ordinary arm: resolve the merge, re-run the janitor, then accept.

    Returns the terminal outcome for the shared tail to journal and emit, or an
    exit code when no single merged pull request resolves.
    """
    merged = _resolved_merge(item=item, plan=plan, runner=runner, journal=journal)
    if isinstance(merged, int):
        return merged
    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=merged,
    )
    if outcome.status != "green" or outcome.stage != "done":
        return outcome
    return outcome_after_acceptance(
        outcome=outcome,
        disposition=complete_and_accept(repo=repo, item=item, outcome=outcome, journal=journal),
    )


def _reaccept_in_acceptance(
    *,
    repo: Path,
    item: WorkItem,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalFile,
) -> DispatchOutcome | int:
    """Re-run ONLY the acceptance pass for an item already resting in `acceptance`.

    The reconcile-merged clause is explicit that such an item's valve "MUST NOT
    re-run the post-merge janitor or re-merge anything": the janitor already ran —
    that is how the merge got there and how the item reached `acceptance` — and a
    second full checkout would spend a provisioning cycle to answer a question
    about records published on the pull request since. So the merge is RESOLVED
    (which is what makes the pull request number and merge sha facts rather than
    assertions) and `post_merge` is deliberately not called.

    The outcome handed to `complete_and_accept` reports `green` at `done` for the
    same reason the re-grade arm's does: the merge the valve just resolved is the
    stronger form of what the telemetry leg asks about, and the stage keeps the
    shared tail's exit code identical between the arms. Every other leg — the
    merged diff, the records, the criteria — the pass reads for itself.

    This is the route by which a record published AFTER the original pass reaches
    a verdict, and by which an item whose pointer was skipped gets one: the pointer
    write lives inside `complete_and_accept`, before any disposition branch.
    """
    merged = _resolved_merge(item=item, plan=plan, runner=runner, journal=journal)
    if isinstance(merged, int):
        return merged
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage="done",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=f"re-ran acceptance against merged PR #{merged.number}; janitor not re-run",
    )
    return outcome_after_acceptance(
        outcome=outcome,
        disposition=complete_and_accept(repo=repo, item=item, outcome=outcome, journal=journal),
    )


def reconcile_plan(
    *, repo: Path, item: WorkItem, janitor: tuple[str, ...] | None, runner: CommandRunner
) -> DispatchPlan:
    """Build the subset of a dispatch plan needed by the reconcile valve.

    It resolves the SAME contract a live dispatch would, from the same two
    sources, because it runs the same post-merge janitor at the same venue: a
    reconcile that resolved its own core pin or its own default branch could
    clean up somewhere the original dispatch never named.
    """
    return build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=repo / "tmp" / f"reconcile-{item.id}-workflow.toml",
        goal_file=repo / "tmp" / f"reconcile-{item.id}-goal.md",
        fabro_bin=resolve_fabro_bin(cwd=repo),
        janitor=janitor,
        janitor_checkout=janitor_reconcile_checkout_path(repo=repo, work_item_id=item.id),
        config_text=livespec_config_text(repo=repo),
        default_branch=resolve_default_branch(repo=repo, runner=runner),
    )


def _reconciled_green(*, outcome: DispatchOutcome) -> bool:
    """Whether this reconcile reconciled the item, across all three arms.

    `acceptance` joins `done` because the acceptance valve now reports where it
    LEFT the item: a re-accept whose pass parked on a PASS is a successful
    reconcile that deliberately did not close, and grading it on `done` alone
    would report every such run as a failure. A NEEDS_ATTENTION park keeps its own
    `needs-attention` status and is still exit 1, which is the parking clause's
    own mapping.
    """
    return outcome.status == "green" and outcome.stage in {"done", ACCEPTANCE_STAGE}


def _outcome_payload(*, outcome: DispatchOutcome) -> dict[str, object]:
    return {
        "work_item_id": outcome.work_item_id,
        "status": outcome.status,
        "stage": outcome.stage,
        "verdict": outcome.verdict,
        "pr_number": outcome.pr_number,
        "merge_sha": outcome.merge_sha,
        "detail": outcome.detail,
        "fabro_run_id": outcome.fabro_run_id,
    }
