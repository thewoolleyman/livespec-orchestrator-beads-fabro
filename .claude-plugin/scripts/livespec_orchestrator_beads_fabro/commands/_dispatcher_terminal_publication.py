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
# `headRefOid` already rides the ordinary view; only the branch NAME has to be
# asked for, and it is what separates this publication from a pull request that
# happens to carry the same head on another branch.
_HEAD_FIELDS = ",headRefName"


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
        # THE CURRENT HOLD, read ONCE for the whole merge-confirmation boundary.
        # The plan's `merge_hold` is the launch snapshot the sandbox and the
        # dispatch record share and must keep; this is what the ledger says now,
        # hours later, and a hold set during the run is visible in exactly one of
        # the two (`_dispatcher_current_merge_hold`).
        hold = read_current_merge_hold(repo=plan.repo, work_item_id=plan.work_item_id)
        view = confirm_pr(plan=plan, runner=runner, journal=journal, hold=hold)
    elif evidence is not None:
        # BOTH EVIDENCE LEGS ARE AUTHENTICATED BEFORE ANY FORGE MUTATION. On this
        # arm the run FAILED, so the only thing that may move a pull request is
        # evidence that this is OUR publication -- and `confirm_pr` arms or
        # disarms auto-merge as its ordinary business. Confirming first and
        # rejecting afterwards therefore mutated a stale or unrelated pull
        # request and only then declined to report it.
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
    """Observe the branch publication with the fields needed to authenticate it.

    A SEPARATE view rather than the one `confirm_pr` already took, because the
    question is different: that one asks whether there is a pull request to
    reconcile, and this one asks whether the pull request in hand is THE
    publication the qualifying checkpoint names. An unreadable view answers no,
    so unavailable evidence keeps the engine's own failed disposition.
    """
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
    """Observe the repository identity that owns this dispatch's publish branch.

    THE THIRD LEG of the publication's identity, and the one a head-and-branch
    comparison cannot supply: a fork carries the same branch name and can carry
    the same head, so without it an unrelated repository's pull request
    authenticates this run's checkpoint.
    """
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
    """Record the two evidence legs, the conflict, and the verdict SEPARATELY.

    Four records rather than one, because they are four different claims and a
    reader has to be able to disbelieve any one of them on its own: what the
    engine concluded, which checkpoint contradicted it, which publication
    authenticated that checkpoint, and only then the classification those three
    support. Collapsing them would leave the conflicting engine evidence
    indistinguishable from the verdict it lost to.
    """
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
            "head": publication.head,
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
