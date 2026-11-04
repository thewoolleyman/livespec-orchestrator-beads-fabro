"""Factory-branch guard for GitHub workflow file changes.

This is a FILE-SCOPED check: it SELECTS the diff files it inspects (those
under `.github/workflows/`) rather than judging the diff as a whole. So its
zero-match case is governed by the scoped-check vacuity clause and reports a
`vacuous-match` outcome rather than a pass -- see
`_dispatcher_scoped_check_vacuity` for why, and for the incident in which THIS
check passed vacuously over an empty merge for all four review rounds.

Note the shape that makes the distinction load-bearing here: this is a
PROHIBITION check, so a matched file is always a fail and its only non-failing
outcome IS vacuity. It has no pass arm to report, which is exactly why reading
its zero matches as green could never have been evidence of anything.

THE RANGE IS NEVER HARD-CODED. The branch the diff is taken against is resolved
through the shared `_dispatcher_default_branch` rule, per
`SPECIFICATION/contracts.md`'s default-branch-resolution clause. Under the
retired `origin/master...HEAD` literal an
adopter whose primary branch is `main` had this guard ask git for a range built
on a ref they do not have -- and `git diff` answers that with a fatal, which
this check reports as an unreadable diff. So the literal did not merely
mis-describe such a repository; it refused it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_scoped_check_vacuity import (
    VACUOUS_MATCH,
    ScopedCheckOutcome,
    gate_exit_code,
    gate_tally,
    scoped_check_outcome,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "FACTORY_WORKFLOW_BOUNDARY_TEXT",
    "WorkflowGuardResult",
    "check_no_workflow_changes",
]

FACTORY_WORKFLOW_BOUNDARY_TEXT = (
    "Factory branches never create/update files under .github/workflows/. "
    "When an implementation needs a workflow change, leave every file "
    "under .github/workflows/ unchanged and report in your final message "
    "that the workflow change routes to the attended host session. A "
    "workflow change lands through the declared workflow-edit route, "
    "under which such an item is refused before dispatch and carried by "
    "the attended host session."
)
_WORKFLOWS_PREFIX = ".github/workflows/"
_DIFF_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class WorkflowGuardResult:
    """Outcome of the workflow-file boundary inspection.

    `outcome` is None on the two arms where the diff was never read -- the
    default branch would not resolve, so no range could be named; or the range
    resolved and `git diff` failed on it. Either way the scope was never
    resolved and there is no matched-file count to call vacuous. That is an
    UNOBSERVABLE check, which is a different thing from a check that observed
    an empty scope, and collapsing the two would hide a broken probe inside the
    vacuity the clause expects to see.
    """

    exit_code: int
    message: str
    outcome: ScopedCheckOutcome | None = None


def check_no_workflow_changes(
    *,
    repo: Path,
    runner: CommandRunner,
) -> WorkflowGuardResult:
    """Fail when the branch diff vs the resolved default branch touches workflow files."""
    branch = resolve_default_branch(repo=repo, runner=runner)
    if branch is None:
        return WorkflowGuardResult(
            exit_code=2,
            message=(
                "workflow guard could not resolve the target's default branch, so there "
                "is no diff range to inspect: neither `git symbolic-ref "
                "refs/remotes/origin/HEAD` nor `gh repo view --json defaultBranchRef` "
                "named one."
            ),
        )
    diff_range = f"origin/{branch}...HEAD"
    diff = runner.run(
        argv=["git", "diff", "--name-only", diff_range],
        cwd=repo,
        timeout_seconds=_DIFF_TIMEOUT_SECONDS,
    )
    if diff.exit_code != 0:
        detail = diff.stderr.strip() or diff.stdout.strip() or "git diff failed"
        return WorkflowGuardResult(
            exit_code=2,
            message=f"workflow guard could not inspect {diff_range}: {detail}",
        )
    diff_paths = _diff_paths(diff_names=diff.stdout)
    workflow_paths = tuple(path for path in diff_paths if path.startswith(_WORKFLOWS_PREFIX))
    outcome = scoped_check_outcome(
        matched_file_count=len(workflow_paths),
        failing=bool(workflow_paths),
    )
    return WorkflowGuardResult(
        exit_code=gate_exit_code(tally=gate_tally(outcomes=(outcome,))),
        message=_message(outcome=outcome, matched=workflow_paths, judged=len(diff_paths)),
        outcome=outcome,
    )


def _message(
    *,
    outcome: ScopedCheckOutcome,
    matched: tuple[str, ...],
    judged: int,
) -> str:
    if outcome == VACUOUS_MATCH:
        return (
            f"vacuous-match: the {_WORKFLOWS_PREFIX} scope matched zero of the {judged} "
            "file(s) in the diff under judgment, so this check OBSERVED NOTHING. That is "
            "not a pass — a gate counts it toward neither passing nor failing."
        )
    return (
        "Factory branch diff touches .github/workflows/, which is out of bounds:\n"
        f"{_format_paths(paths=matched)}\n\n"
        f"{FACTORY_WORKFLOW_BOUNDARY_TEXT}"
    )


def _diff_paths(*, diff_names: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in diff_names.splitlines() if line.strip())


def _format_paths(*, paths: tuple[str, ...]) -> str:
    return "\n".join(f"- {path}" for path in paths)
