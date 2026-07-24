"""Source-checkout preflight for Fabro dispatch staging safety."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "SourceCheckoutRefusal",
    "journal_source_checkout_refusal",
    "source_checkout_preflight_refusal",
]

_GIT_PREFLIGHT_TIMEOUT_SECONDS = 30.0
_MAX_UNPUSHED_COMMITS = 20
_STAGE = "source-checkout-origin-reachability"
_REASON = "source-head-not-origin-reachable"
_REMEDY = (
    "Remedy: preserve the unpushed commit(s) on a branch/worktree, then "
    "reset the primary checkout to origin/master before dispatching. Do not "
    "push from the primary checkout; the commit-refuse hook correctly forbids "
    "that path."
)


@dataclass(frozen=True, kw_only=True)
class SourceCheckoutRefusal:
    """Terminal source-checkout preflight refusal, ready to emit and journal."""

    detail: str
    record: dict[str, object]


def source_checkout_preflight_refusal(
    *, repo: Path, runner: CommandRunner
) -> SourceCheckoutRefusal | None:
    """Refuse when `repo` HEAD is not contained by any `origin/*` ref.

    Non-git paths are left to the existing repo/workflow precondition check so
    this staging guard stays scoped to real source checkouts. A git checkout
    with no usable `origin` refs is unsafe for Fabro snapshot staging and fails
    closed, because the resulting base cannot be proven origin-reachable.
    """
    if not _is_git_worktree(repo=repo, runner=runner):
        return None
    origin_refs = _origin_refs(repo=repo, runner=runner)
    reachable = any(_head_is_ancestor(repo=repo, runner=runner, ref=ref) for ref in origin_refs)
    if reachable:
        return None
    unpushed = _unpushed_commits(repo=repo, runner=runner)
    push = _dry_run_source_push(repo=repo, runner=runner)
    head = _git_stdout(repo=repo, runner=runner, argv=["rev-parse", "--short", "HEAD"])
    return SourceCheckoutRefusal(
        detail=_refusal_detail(head=head, unpushed=unpushed, push=push),
        record=_refusal_record(head=head, origin_refs=origin_refs, unpushed=unpushed, push=push),
    )


def journal_source_checkout_refusal(*, journal_path: Path, refusal: SourceCheckoutRefusal) -> None:
    """Persist the distinct terminal preflight outcome in the dispatch journal."""
    JournalFile(path=journal_path).append(record=refusal.record)


def _is_git_worktree(*, repo: Path, runner: CommandRunner) -> bool:
    result = _git(repo=repo, runner=runner, argv=["rev-parse", "--is-inside-work-tree"])
    return result.exit_code == 0 and result.stdout.strip() == "true"


def _origin_refs(*, repo: Path, runner: CommandRunner) -> tuple[str, ...]:
    result = _git(
        repo=repo,
        runner=runner,
        argv=["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
    )
    if result.exit_code != 0:
        return ()
    return tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and line.strip() != "origin/HEAD"
    )


def _head_is_ancestor(*, repo: Path, runner: CommandRunner, ref: str) -> bool:
    result = _git(repo=repo, runner=runner, argv=["merge-base", "--is-ancestor", "HEAD", ref])
    return result.exit_code == 0


def _unpushed_commits(*, repo: Path, runner: CommandRunner) -> tuple[str, ...]:
    result = _git(
        repo=repo,
        runner=runner,
        argv=[
            "log",
            "--oneline",
            "--decorate",
            f"--max-count={_MAX_UNPUSHED_COMMITS}",
            "HEAD",
            "--not",
            "--remotes=origin",
        ],
    )
    if result.exit_code != 0:
        return (f"<unable to list unpushed commits: {result.stderr.strip()}>",)
    commits = tuple(line for line in result.stdout.splitlines() if line)
    return commits or ("<no unpushed commits listed; origin reachability still failed>",)


def _dry_run_source_push(*, repo: Path, runner: CommandRunner) -> CommandResult:
    branch = _git_stdout(repo=repo, runner=runner, argv=["rev-parse", "--abbrev-ref", "HEAD"])
    target = branch if branch and branch != "HEAD" else "master"
    return _git(repo=repo, runner=runner, argv=["push", "--dry-run", "origin", f"HEAD:{target}"])


def _git_stdout(*, repo: Path, runner: CommandRunner, argv: list[str]) -> str:
    result = _git(repo=repo, runner=runner, argv=argv)
    return result.stdout.strip() if result.exit_code == 0 else ""


def _git(*, repo: Path, runner: CommandRunner, argv: list[str]) -> CommandResult:
    return runner.run(
        argv=["git", *argv],
        cwd=repo,
        timeout_seconds=_GIT_PREFLIGHT_TIMEOUT_SECONDS,
    )


def _refusal_detail(*, head: str, unpushed: tuple[str, ...], push: CommandResult) -> str:
    commits = "\n".join(f"  {commit}" for commit in unpushed)
    push_outcome = _push_outcome_text(push=push)
    return (
        "ERROR: source checkout HEAD is not reachable from any origin ref; "
        "refusing dispatch before sandbox work.\n"
        f"HEAD: {head or '<unknown>'}\n"
        "Unpushed commit(s):\n"
        f"{commits}\n"
        "Pre-clone source push outcome (dry-run):\n"
        f"{push_outcome}\n"
        f"{_REMEDY}\n"
    )


def _push_outcome_text(*, push: CommandResult) -> str:
    stdout = push.stdout.strip() or "<empty stdout>"
    stderr = push.stderr.strip() or "<empty stderr>"
    return f"  exit_code={push.exit_code}\n  stdout={stdout}\n  stderr={stderr}"


def _refusal_record(
    *,
    head: str,
    origin_refs: tuple[str, ...],
    unpushed: tuple[str, ...],
    push: CommandResult,
) -> dict[str, object]:
    return {
        "stage": _STAGE,
        "terminal": True,
        "status": "failed",
        "reason": _REASON,
        "head": head,
        "origin_refs": list(origin_refs),
        "unpushed_commits": list(unpushed),
        "push_outcome": {
            "exit_code": push.exit_code,
            "stdout": push.stdout,
            "stderr": push.stderr,
        },
        "remedy": _REMEDY,
    }
