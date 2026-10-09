"""Authenticate terminal-conflict publication through a dedicated forge view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    CurrentMergeHold,
    read_current_merge_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import confirm_pr
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
    pr_view_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = [
    "TerminalPublication",
    "reconcile_terminal_publication",
    "terminal_publication_matches",
]

_GH_TIMEOUT_SECONDS = 300.0
_HEAD_FIELDS = ",headRefName,headRefOid"


@dataclass(frozen=True, kw_only=True)
class TerminalPublication:
    """The normal PR view plus any terminal failure publication could not override."""

    hold: CurrentMergeHold
    view: PrView | None
    refusal: DispatchOutcome | None


def reconcile_terminal_publication(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    terminal: DispatchOutcome | None,
    checkpoint_head: str | None,
) -> TerminalPublication:
    """Confirm a PR only for a normally-green or checkpoint-qualified run."""
    hold: CurrentMergeHold = "unreadable"
    view = None
    if terminal is None or checkpoint_head is not None:
        hold = read_current_merge_hold(repo=plan.repo, work_item_id=plan.work_item_id)
        view = confirm_pr(plan=plan, runner=runner, journal=journal, hold=hold)
    matches = bool(
        view is not None
        and checkpoint_head is not None
        and terminal_publication_matches(
            plan=plan,
            runner=runner,
            journal=journal,
            pr_number=view.number,
            head=checkpoint_head,
        )
    )
    refusal = terminal if terminal is not None and not matches else None
    return TerminalPublication(hold=hold, view=view, refusal=refusal)


def terminal_publication_matches(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    pr_number: int,
    head: str,
) -> bool:
    """Observe and match the branch, PR identity, state, and checkpoint head."""
    argv = pr_view_argv(plan=plan)
    argv[-1] = f"{argv[-1]}{_HEAD_FIELDS}"
    result = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="fabro-terminal-publication",
        result=result,
    )
    view = parse_pr_view(stdout=result.stdout) if result.exit_code == 0 else None
    return bool(
        view is not None
        and view.number == pr_number
        and view.matches_publication(branch=plan.branch, head=head)
    )
