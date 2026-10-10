"""Merge and post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_pr_association import (
    pr_view_for_merge_sha,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
    pr_arm_argv,
    pr_disarm_argv,
    pr_update_branch_argv,
    pr_view_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
        CurrentMergeHold,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
        PollPolicy,
        SleepFn,
    )

__all__: list[str] = ["await_merge", "confirm_pr", "outcome_after_await"]

_GH_TIMEOUT_SECONDS = 300.0
_PUBLICATION_FIELDS = ",headRefName,headRefOid,headRepository"


def confirm_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    hold: CurrentMergeHold,
    expected_publication: PrView | None = None,
) -> PrView | None:
    """Confirm the publish branch's pull request, arming auto-merge only if it may.

    `hold` is the CURRENT merge hold, read once at this boundary from the ledger
    authority rather than taken off `plan.merge_hold`
    (`_dispatcher_current_merge_hold` records why). It is a parameter rather than a
    read of its own because the terminal classification downstream must route on the
    SAME reading: two reads of one question cannot be proven to agree, and their
    disagreement would be invisible -- both return a well-formed answer.

    A MERGED pull request is past the hold entirely and is returned before `hold` is
    consulted at all: the ratified valve refuses a hold on a merged item as a no-op
    naming the merge, so there is nothing here to hold and nothing to arm.
    """
    view = _view_pr(
        plan=plan,
        runner=runner,
        journal=journal,
        include_publication=expected_publication is not None,
    )
    if view is None or not _matches_expected_publication(
        view=view,
        expected=expected_publication,
    ):
        return None
    if view.state == "MERGED":
        return view
    if hold == "unheld":
        confirmed = _arm_fallback(
            plan=plan,
            runner=runner,
            journal=journal,
            view=view,
            include_publication=expected_publication is not None,
        )
    elif hold == "held" and view.auto_merge_armed:
        confirmed = _disarm_held(
            plan=plan,
            runner=runner,
            journal=journal,
            view=view,
            include_publication=expected_publication is not None,
        )
    else:
        # The two write-nothing readings. A held pull request with nothing armed is
        # already in the state the hold wants. An `unreadable` authority is NOT that same
        # state -- it is this host declining to answer for a ledger it could not ask, so
        # it makes no forge write in EITHER direction: arming would reverse a hold it
        # cannot see, and disarming would reverse an arming it cannot justify.
        confirmed = view
    return (
        confirmed
        if confirmed is not None
        and _matches_expected_publication(view=confirmed, expected=expected_publication)
        else None
    )


def _arm_fallback(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    view: PrView,
    include_publication: bool,
) -> PrView | None:
    """Arm auto-merge for an unheld pull request that is not armed already."""
    if view.auto_merge_armed:
        return view
    argv = pr_arm_argv(plan=plan, number=view.number)
    # An EMPTY argv is the LAUNCH snapshot's own hold saying there is no forge write
    # to make. It still stands with the ledger reading unheld: a hold released
    # mid-run is armed by the release valve itself, from the merge method the
    # dispatch journaled, and this seam has no business re-arming behind it.
    if not argv:
        return view
    arm = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-arm-fallback", result=arm)
    return _view_pr(
        plan=plan,
        runner=runner,
        journal=journal,
        include_publication=include_publication,
    )


def _disarm_held(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    view: PrView,
    include_publication: bool,
) -> PrView | None:
    """Remove an auto-merge request from a pull request the ledger now holds.

    Leaving it armed would honour the hold's letter -- this confirmation armed
    nothing -- while the merge the hold forbids lands anyway on the next green check
    run. The arming is almost always this host's own, from a dispatch that read the
    stale snapshot, so refusing to undo it would leave the measured defect's effect
    standing while fixing only its cause.

    The disarm command's result is JOURNALED and deliberately not routed on, because
    it decides nothing: the re-read below is the authoritative post-condition, and
    `merge_hold_terminal` refuses on a view that still carries an auto-merge request
    whatever the command said. That cuts both ways -- a failed write whose pull
    request is nonetheless unarmed is a hold that holds, and a successful write whose
    pull request is still armed is one that does not. The journal row is where an
    operator tells those two apart.
    """
    disarm = runner.run(
        argv=pr_disarm_argv(plan=plan, number=view.number),
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-disarm-held", result=disarm)
    return _view_pr(
        plan=plan,
        runner=runner,
        journal=journal,
        include_publication=include_publication,
    )


def await_merge(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
) -> PrView | DispatchOutcome | None:
    for attempt in range(poll.attempts):
        view = _view_pr(plan=plan, runner=runner, journal=journal)
        if view is not None and view.state == "MERGED":
            return view
        if view is not None and view.merge_state_status == "BEHIND":
            update = runner.run(
                argv=pr_update_branch_argv(plan=plan, number=view.number),
                cwd=plan.repo,
                timeout_seconds=_GH_TIMEOUT_SECONDS,
            )
            journal_stage(journal=journal, plan=plan, stage="pr-update-branch", result=update)
        elif view is not None and view.terminal_required_check_failures:
            checks = ", ".join(view.terminal_required_check_failures)
            return outcome_type(
                work_item_id=plan.work_item_id,
                status="failed",
                stage="merge-poll",
                pr_number=view.number,
                merge_sha=view.merge_sha,
                detail=f"required check failed terminally: {checks}",
            )
        if attempt + 1 < poll.attempts:
            sleep(poll.interval_seconds)
    return None


def outcome_after_await(  # noqa: PLR0913 — kw-only disposition; each field is an independent caller input.
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView | DispatchOutcome | None,
    pr_number: int,
    run_id: str | None,
) -> DispatchOutcome:
    """One terminal outcome from `await_merge`'s three-way answer.

    The poll reports a MERGED view, a terminal failure it already decided (a
    required check that failed for good), or an exhausted budget, and each is a
    different outcome. It lives beside the poll rather than inside `run_dispatch`
    so that function stays one readable list of stages rather than a stage list
    with a disposition tree hanging off its end.
    """
    # Discriminated on `PrView` rather than on `outcome_type`, which is a
    # runtime PARAMETER and so narrows nothing for the reader or the checker.
    if isinstance(merged, PrView):
        return post_merge(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            merged=pr_view_for_merge_sha(
                repo=plan.repo,
                work_item_id=plan.work_item_id,
                merged=merged,
                runner=runner,
                journal=journal,
            ),
        )
    if merged is None:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="merge-poll",
            pr_number=pr_number,
            merge_sha=None,
            detail="PR did not reach MERGED within the poll budget",
            fabro_run_id=run_id,
        )
    return merged


def _view_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    include_publication: bool = False,
) -> PrView | None:
    argv = pr_view_argv(plan=plan)
    if include_publication:
        argv[-1] = f"{argv[-1]}{_PUBLICATION_FIELDS}"
    result = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-view", result=result)
    if result.exit_code != 0:
        return None
    return parse_pr_view(stdout=result.stdout)


def _matches_expected_publication(*, view: PrView, expected: PrView | None) -> bool:
    """Require every terminal-conflict re-read to name the authenticated PR."""
    if expected is None:
        return True
    branch = expected.head_ref_name
    head = expected.head_ref_oid
    repository = expected.head_repository
    return bool(
        branch
        and head
        and repository
        and view.number == expected.number
        and view.matches_publication(branch=branch, head=head, repository=repository)
    )
