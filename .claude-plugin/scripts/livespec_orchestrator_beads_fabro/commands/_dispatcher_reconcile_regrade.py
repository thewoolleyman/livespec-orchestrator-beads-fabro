"""The re-GRADE arm of the `reconcile-merged` valve.

An item whose pull request merged green and whose post-merge acceptance then
FAILED is stamped `rework:pending` and left `active`. When that failure was the
CRITERIA's rather than the code's — a prohibition-shaped fragment no correct
implementation can evidence — every route back to a verdict is closed. The
plain reconcile valve refuses the marker (its disposition already ran and chose
rework), the human `accept` valve refuses the `active` source state, and the
designated rework re-dispatch re-IMPLEMENTS work that is already on the default
branch, so it cuts an empty branch, fails the changed-tree stage, and spends an
`acceptance_rework_cap` attempt — converting a recoverable state into
`blocked` / needs-human on the last one.

This arm is that missing route, and it is deliberately a RE-GRADE rather than a
carve-out. It disposes of nothing on an operator's say-so: it proceeds only
when the merged pull request RESOLVES from the forge and its merge commit is an
ancestor of the default branch's tip — two facts about the repository an
invocation cannot fabricate — and it then runs the SAME acceptance pass the
dispatch path runs, against the item's CURRENT effective criteria. Passing
`--regrade` selects the arm; it never supplies the evidence.

A pass that grades anything other than PASS leaves the item exactly as it found
it — status, labels and `acceptance_failed_ai_passes` alike. A re-grade is not
a second chance to fail: an operator who mis-repaired the criteria must be able
to try again, and an arm that charged the rework cap for looking would burn the
item it exists to recover.

It never launches a Fabro run, cuts a branch, or re-runs the post-merge
janitor. The janitor already ran for this item — that is how the merge got
there — and re-running it would spend a full checkout to answer a question
about criteria text.
"""

from __future__ import annotations

from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_close import (
    close_dispatch_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    janitor_venue_contains_merge_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged_pr import (
    resolve_merged_pr,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ACCEPTANCE_POLICY,
    effective_acceptance_policy,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "MERGE_CONTAINMENT_STAGE",
    "REGRADE_STAGE",
    "run_regrade",
]

REGRADE_STAGE = "regrade"
MERGE_CONTAINMENT_STAGE = "regrade-merge-containment"
_CONTAINMENT_TIMEOUT_SECONDS = 30.0
_UNMERGED_REFUSAL = (
    "ERROR: reconcile-merged --regrade refused: no merged PR resolves for work-item "
    "{item_id}, so there is no merged diff to re-grade against. The arm keys on the "
    "merge itself; drive the fix-forward rework re-dispatch instead.\n"
)
_UNCONTAINED_REFUSAL = (
    "ERROR: reconcile-merged --regrade refused: the merge commit {merge_sha} of PR "
    "#{pr_number} for work-item {item_id} is not an ancestor of {tip}, so this "
    "repository cannot show the work landed on the default branch. Fetch {tip} and "
    "retry, or drive the fix-forward rework re-dispatch instead.\n"
)


def run_regrade(
    *,
    repo: Path,
    item: WorkItem,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalFile,
) -> DispatchOutcome | int:
    """Re-grade a merged, rework-pending item against its current criteria.

    Returns the terminal `DispatchOutcome` for the caller to journal and emit —
    green at `done` when the re-grade PASSES and the item closes, failed at
    `regrade` when it reaches any other verdict and the item is untouched — or
    an exit code when the merge evidence the arm keys on does not hold.
    """
    merged = resolve_merged_pr(plan=plan, item=item, runner=runner, journal=journal)
    if isinstance(merged, str):
        _ = write_stderr(text=merged)
        return EXIT_PRECONDITION_ERROR
    if merged is None:
        _ = write_stderr(text=_UNMERGED_REFUSAL.format(item_id=item.id))
        return EXIT_PRECONDITION_ERROR
    containment = _merge_containment_refusal(
        plan=plan, item=item, merged=merged, runner=runner, journal=journal
    )
    if containment is not None:
        _ = write_stderr(text=containment)
        return EXIT_PRECONDITION_ERROR
    return _grade_and_dispose(repo=repo, item=item, merged=merged, runner=runner, journal=journal)


def _merge_containment_refusal(
    *,
    plan: DispatchPlan,
    item: WorkItem,
    merged: PrView,
    runner: CommandRunner,
    journal: JournalFile,
) -> str | None:
    """Refuse unless the resolved merge commit is an ancestor of the default branch.

    The tip is `origin/<default branch>` read off the plan's ONE resolved
    contract, exactly as the janitor venue resolves its own, so the arm and the
    dispatch path cannot come to name two different branches. A commit is its
    own ancestor, so a tip that IS the merge answers yes.

    This is the half of the evidence an operator cannot assert: a forge that
    reports a merged pull request says the pull request merged, while the
    ancestry says THIS repository can see the work on the branch it is about to
    close the item against.
    """
    tip = f"origin/{plan.integration.contract.default_branch}"
    merge_sha = merged.merge_sha
    if merge_sha is None:  # pragma: no cover - resolve_merged_pr yields only sha-bearing views
        return _UNMERGED_REFUSAL.format(item_id=item.id)
    contains = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage=MERGE_CONTAINMENT_STAGE,
        command=(
            janitor_venue_contains_merge_argv(plan=plan, tip=tip, merge_sha=merge_sha),
            plan.repo,
            _CONTAINMENT_TIMEOUT_SECONDS,
            None,
        ),
    )
    if contains.exit_code != 0:
        return _UNCONTAINED_REFUSAL.format(
            merge_sha=merge_sha, pr_number=merged.number, item_id=item.id, tip=tip
        )
    return None


def _grade_and_dispose(
    *,
    repo: Path,
    item: WorkItem,
    merged: PrView,
    runner: CommandRunner,
    journal: JournalFile,
) -> DispatchOutcome:
    """Run the acceptance pass over the verified merge and dispose on PASS alone.

    The outcome handed to the pass reports `green` because the merge evidence
    the arm just verified is what the telemetry leg asks about, and it is the
    STRONGER form of it: a run status is a claim about a process that has since
    exited, while the ancestry is a fact about the branch this repository can
    read. Every other leg — the merged diff, the effective criteria — the pass
    reads for itself, so nothing here is asserted on the arm's behalf.

    The effective `acceptance_policy` is journaled and deliberately does NOT
    gate the disposition. `--regrade` is an attributed operator act rather than
    an automatic pass, so the invocation IS the human judgement a `human-only`
    item asks for, and the graded criteria are the evidence behind it.
    """
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage=REGRADE_STAGE,
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=f"re-grading against merged PR #{merged.number}",
    )
    # The item's declared ledger markers carry the change-optional exemption; an
    # unreadable label set is NOT a declaration, so it fails closed to the empty
    # marker set exactly as the dispatch-path acceptance valve does.
    labels = read_dispatch_labels(repo=repo, item=item)
    result = run_acceptance_pass(
        repo=repo,
        item=item,
        outcome=outcome,
        runner=runner,
        raw_labels=() if isinstance(labels, str) else labels,
    )
    # `unsafe_perform_io` is required: `IOResult.value_or` returns `IO[value]`.
    policy = unsafe_perform_io(
        effective_acceptance_policy(item=item, cwd=repo).value_or(DEFAULT_ACCEPTANCE_POLICY)
    )
    journal.append(record=result.journal_record(work_item_id=item.id, policy=policy))
    # The literal matches the dispatch-path acceptance valve's own comparison;
    # a named constant here reads to the lint rule set as a hardcoded secret.
    if result.verdict != "PASS":
        return _leave_regraded_item(item=item, outcome=outcome, verdict=result.verdict)
    return _close_regraded_item(repo=repo, item=item, outcome=outcome, journal=journal)


def _close_regraded_item(
    *, repo: Path, item: WorkItem, outcome: DispatchOutcome, journal: JournalFile
) -> DispatchOutcome:
    """Close a re-graded PASS, which is what clears the `rework:pending` marker.

    The marker is NOT cleared by a second write of its own. Every lifecycle
    write seam carries `rework_pending_label_removals`, so the close that lands
    `done` removes the label in the SAME mutation — that is the structural
    guarantee `_store_rework_mutations` exists to give, and a disposition that
    cleared the marker by hand would be re-asserting what the seam already
    holds, in a second write that can fail on its own.
    """
    close_dispatch_item(
        repo=repo,
        item=item,
        outcome=outcome,
        resolution="completed",
        reason=(
            f"reconcile-merged --regrade: acceptance re-graded PASS against merged "
            f"PR #{outcome.pr_number} ({outcome.merge_sha})"
        ),
    )
    journal.append(record={"stage": "ledger-regrade-accept", "work_item_id": item.id})
    return DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage="done",
        pr_number=outcome.pr_number,
        merge_sha=outcome.merge_sha,
        detail="re-graded PASS, rework:pending cleared and item closed",
    )


def _leave_regraded_item(
    *, item: WorkItem, outcome: DispatchOutcome, verdict: str
) -> DispatchOutcome:
    """Report a non-PASS re-grade, having written nothing at all.

    There is no ledger call on this path, which is the whole point: the item's
    status, its `rework:pending` marker and its `acceptance_failed_ai_passes`
    metadata stay exactly as the ORIGINAL failing disposition wrote them, and a
    re-grade that could not clear the item must not charge it for the attempt.
    """
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} re-graded {verdict} against merged PR "
            f"#{outcome.pr_number}; left unchanged at {item.status} with rework:pending "
            "and its acceptance_failed_ai_passes intact. Repair the effective "
            "acceptance criteria and re-run --regrade.\n"
        )
    )
    return DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage=REGRADE_STAGE,
        pr_number=outcome.pr_number,
        merge_sha=outcome.merge_sha,
        detail=f"re-graded {verdict}; item left unchanged",
    )
