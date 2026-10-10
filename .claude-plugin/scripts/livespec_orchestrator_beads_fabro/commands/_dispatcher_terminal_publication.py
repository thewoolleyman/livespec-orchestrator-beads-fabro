"""Authenticate terminal-conflict publication through a dedicated forge view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

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
from livespec_orchestrator_beads_fabro.effects import parse_json

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
    matches = False
    if terminal is None:
        hold = read_current_merge_hold(repo=plan.repo, work_item_id=plan.work_item_id)
        view = confirm_pr(plan=plan, runner=runner, journal=journal, hold=hold)
    elif evidence is not None:
        observed = terminal_publication_view(plan=plan, runner=runner, journal=journal)
        repository = (
            terminal_repository_name(plan=plan, runner=runner, journal=journal)
            if observed is not None
            else None
        )
        authenticated = observed is not None and observed.matches_publication(
            branch=plan.branch,
            head=evidence.commit_sha,
            repository=repository or "",
        )
        if authenticated and observed is not None:
            hold = read_current_merge_hold(repo=plan.repo, work_item_id=plan.work_item_id)
            view = confirm_pr(
                plan=plan,
                runner=runner,
                journal=journal,
                hold=hold,
                expected_publication=observed,
            )
            matches = view is not None
        if matches and view is not None:
            _journal_successful_classification(
                plan=plan,
                journal=journal,
                evidence=evidence,
                publication=view,
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


def terminal_repository_name(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> str | None:
    """Observe the repository identity that owns this dispatch's publish branch."""
    result = runner.run(
        argv=["gh", "repo", "view", "--json", "nameWithOwner"],
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="fabro-terminal-repository-probe",
        result=result,
    )
    if result.exit_code != 0:
        return None
    parsed_raw = parse_json(text=result.stdout)
    if not isinstance(parsed_raw, dict):
        return None
    return cast("str | None", cast("dict[str, object]", parsed_raw).get("nameWithOwner"))


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
