"""Confirm the publish branch's pull request, and arm or disarm auto-merge.

Split out of `_dispatcher_engine_merge` by cohesion: that module owns what
happens AFTER a pull request is confirmed (polling it to MERGED, then the
post-merge janitor), while this owns the confirmation itself and the two forge
WRITES it may make. `_arm_fallback`, `_disarm_held` and
`_matches_expected_publication` are private to this module because `confirm_pr`
is their only caller; the pull-request READ they share with the merge poll lives
in `_dispatcher_pr_view` as a public interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    pr_arm_argv,
    pr_disarm_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import (
    GH_TIMEOUT_SECONDS,
    PrViewReading,
    view_pr,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
        CurrentMergeHold,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        JournalWriter,
    )

__all__: list[str] = ["confirm_pr", "confirm_pr_reading"]


def confirm_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    hold: CurrentMergeHold,
    expected_publication: PrView | None = None,
) -> PrView | None:
    """Confirm a pull request for callers that need only its observed view."""
    return confirm_pr_reading(
        plan=plan,
        runner=runner,
        journal=journal,
        hold=hold,
        expected_publication=expected_publication,
    ).view


def confirm_pr_reading(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    hold: CurrentMergeHold,
    expected_publication: PrView | None = None,
) -> PrViewReading:
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
    reading = view_pr(
        plan=plan,
        runner=runner,
        journal=journal,
        include_publication=expected_publication is not None,
        include_status_checks=False,
    )
    view = reading.view
    if view is None:
        return reading
    if not _matches_expected_publication(view=view, expected=expected_publication):
        return PrViewReading(view=None, error=reading.error)
    if view.state == "MERGED":
        return reading
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
        confirmed = PrViewReading(view=view, error=None)
    confirmed_view = confirmed.view
    return (
        confirmed
        if confirmed_view is not None
        and _matches_expected_publication(view=confirmed_view, expected=expected_publication)
        else PrViewReading(view=None, error=confirmed.error)
    )


def _arm_fallback(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    view: PrView,
    include_publication: bool,
) -> PrViewReading:
    """Arm auto-merge for an unheld pull request that is not armed already."""
    if view.auto_merge_armed:
        return PrViewReading(view=view, error=None)
    argv = pr_arm_argv(plan=plan, number=view.number)
    # An EMPTY argv is the LAUNCH snapshot's own hold saying there is no forge write
    # to make. It still stands with the ledger reading unheld: a hold released
    # mid-run is armed by the release valve itself, from the merge method the
    # dispatch journaled, and this seam has no business re-arming behind it.
    if not argv:
        return PrViewReading(view=view, error=None)
    arm = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-arm-fallback", result=arm)
    return view_pr(
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
) -> PrViewReading:
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
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-disarm-held", result=disarm)
    return view_pr(
        plan=plan,
        runner=runner,
        journal=journal,
        include_publication=include_publication,
    )


def _matches_expected_publication(*, view: PrView, expected: PrView | None) -> bool:
    """Require every terminal-conflict re-read to name the authenticated PR.

    `confirm_pr` takes its OWN view, and arms or disarms from it, so the pull
    request it acts on need not be the one an earlier read authenticated: a
    publication that changes between the two reads would otherwise be mutated,
    and then reported, on the strength of the stale reading. With no expected
    publication supplied this is the ordinary green path and imposes nothing.
    """
    if expected is None:
        return True
    branch = expected.head_ref_name
    head = expected.head
    repository = expected.head_repository
    return bool(
        branch
        and head
        and repository
        and view.number == expected.number
        and view.matches_publication(branch=branch, head=head, repository=repository)
    )
