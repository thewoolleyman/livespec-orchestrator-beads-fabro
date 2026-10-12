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
from livespec_orchestrator_beads_fabro.commands._dispatcher_successful_terminal import (
    SuccessfulTerminalEvidence,
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
    "terminal_publication_view",
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
    evidence: SuccessfulTerminalEvidence | None,
) -> TerminalPublication:
    """Confirm a PR only for a normally-green or checkpoint-qualified run."""
    hold: CurrentMergeHold = "unreadable"
    view = None
    if terminal is None or evidence is not None:
        hold = read_current_merge_hold(repo=plan.repo, work_item_id=plan.work_item_id)
        view = confirm_pr(plan=plan, runner=runner, journal=journal, hold=hold)
    observed = (
        terminal_publication_view(plan=plan, runner=runner, journal=journal)
        if view is not None and evidence is not None
        else None
    )
    matches = False
    if observed is not None and view is not None and evidence is not None:
        matches = observed.number == view.number and observed.matches_publication(
            branch=plan.branch,
            head=evidence.commit_sha,
        )
        if matches:
            _journal_successful_classification(
                plan=plan,
                journal=journal,
                evidence=evidence,
                publication=observed,
            )
    refusal = terminal if terminal is not None and not matches else None
    return TerminalPublication(hold=hold, view=view, refusal=refusal)


def terminal_publication_view(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> PrView | None:
    """Observe the branch publication with the fields needed to authenticate it."""
    argv = pr_view_argv(plan=plan)
    argv[-1] = f"{argv[-1]}{_HEAD_FIELDS},headRepository"
    result = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="fabro-terminal-publication-probe",
        result=result,
    )
    return parse_pr_view(stdout=result.stdout) if result.exit_code == 0 else None


def _journal_successful_classification(
    *,
    plan: DispatchPlan,
    journal: JournalWriter,
    evidence: SuccessfulTerminalEvidence,
    publication: PrView,
) -> None:
    common: dict[str, object] = {
        "work_item_id": plan.work_item_id,
        "run_id": evidence.run_id,
    }
    journal.append(
        record={
            **common,
            "stage": "fabro-terminal-conflict",
            "engine_status": evidence.engine_status,
            "failure_cause": evidence.failure_cause,
            "failure_category": evidence.failure_category,
        }
    )
    journal.append(
        record={
            **common,
            "stage": "fabro-terminal-checkpoint",
            "timestamp": evidence.timestamp,
            "current_node": evidence.current_node,
            "next_node_id": evidence.next_node_id,
            "commit_sha": evidence.commit_sha,
        }
    )
    journal.append(
        record={
            **common,
            "stage": "fabro-terminal-publication",
            "pr_number": publication.number,
            "state": publication.state,
            "branch": publication.head_ref_name,
            "head": publication.head_ref_oid,
            "repository": publication.head_repository,
        }
    )
    journal.append(
        record={
            **common,
            "stage": "fabro-terminal-classification",
            "classification": "successful-workflow",
            "evidence": "checkpoint+publication",
        }
    )
