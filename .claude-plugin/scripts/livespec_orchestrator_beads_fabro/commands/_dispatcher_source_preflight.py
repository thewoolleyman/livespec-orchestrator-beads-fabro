"""Source-checkout preflight for Fabro dispatch staging safety.

THREE SANCTIONED OUTCOMES, NO FOURTH. The step proves that the base Fabro will
stage from the dispatch target is reachable from an `origin/*` ref. It passes
when it is, refuses when it is not -- and refuses when it CANNOT TELL, which is
the arm that used to be a silent skip. A path that is not a Git worktree was
previously left to the repo/workflow precondition check and the dispatch
proceeded; that is proceed-and-hope on the one question this step exists to
answer, and it is indistinguishable at the call site from a proven-clean
checkout. Absence of proof is refusal.

WHAT is looked up lives here; HOW an outcome reads lives in
`_dispatcher_source_refusals`. WHERE it is journaled is neither: the
pre-dispatch step gate owns one journal handle and appends every step's record
through it, so this module decides and says nothing about persistence.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_refusals import (
    SourceCheckoutOutcome,
    SourceCheckoutRefusal,
    not_a_worktree_outcome,
    pass_outcome,
    unreachable_outcome,
)

__all__: list[str] = [
    "SourceCheckoutOutcome",
    "SourceCheckoutRefusal",
    "source_checkout_preflight",
]

_GIT_PREFLIGHT_TIMEOUT_SECONDS = 30.0
_MAX_UNPUSHED_COMMITS = 20

# The synthesized outcome of a dry-run push that was never attempted, because a
# detached HEAD on a repository whose default branch neither resolution route
# would name leaves no ref to push at. A non-zero code so a reader tallying the
# quoted outcome cannot read it as a push that succeeded.
_UNNAMEABLE_TARGET_EXIT = 1
_NO_TARGET_DETAIL = (
    "HEAD is detached and neither `git symbolic-ref refs/remotes/origin/HEAD` nor "
    "`gh repo view --json defaultBranchRef` named a default branch, so there is no "
    "branch to dry-run a push at\n"
)


def source_checkout_preflight(*, repo: Path, runner: CommandRunner) -> SourceCheckoutOutcome:
    """Prove `repo` HEAD is contained by some `origin/*` ref, or refuse.

    A git checkout with no usable `origin` refs is unsafe for Fabro snapshot
    staging and fails closed, because the resulting base cannot be proven
    origin-reachable; a path that is not a git checkout at all fails closed for
    the same reason one step earlier.
    """
    if not _is_git_worktree(repo=repo, runner=runner):
        return not_a_worktree_outcome(repo=str(repo))
    origin_refs = _origin_refs(repo=repo, runner=runner)
    head = _git_stdout(repo=repo, runner=runner, argv=["rev-parse", "HEAD"])
    origin_ref = next(
        (
            ref
            for ref in origin_refs
            if head and _head_is_ancestor(repo=repo, runner=runner, head=head, ref=ref)
        ),
        None,
    )
    if origin_ref is not None:
        return pass_outcome(head=head, origin_refs=origin_refs, origin_ref=origin_ref)
    return unreachable_outcome(
        head=head,
        origin_refs=origin_refs,
        unpushed=_unpushed_commits(repo=repo, runner=runner),
        push=_dry_run_source_push(repo=repo, runner=runner),
    )


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


def _head_is_ancestor(*, repo: Path, runner: CommandRunner, head: str, ref: str) -> bool:
    result = _git(repo=repo, runner=runner, argv=["merge-base", "--is-ancestor", head, ref])
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
    """The dry-run push whose outcome the refusal quotes, onto a NAMED branch.

    A detached HEAD names no branch of its own, so the target falls back to the
    repository's own default branch through the ONE shared two-route resolution
    the ratified default-branch-resolution clause names. It used to fall back to
    a branch name this fleet happens to use, which on an adopter dry-ran against
    a ref they do not have and reported that ref's absence as the push outcome --
    diagnostic evidence about our assumption rather than about their checkout.

    This step has no dispatch plan in scope: it runs before one is built, on a
    repository whose contract has not been resolved. So it resolves the branch
    itself, through the shared resolver rather than through a constant.

    When neither route names a branch there is no target to push at, and the
    outcome SAYS so rather than pushing at a guess. It is evidence inside a
    refusal that has already been decided, so this cannot mask a pass.
    """
    branch = _git_stdout(repo=repo, runner=runner, argv=["rev-parse", "--abbrev-ref", "HEAD"])
    target = (
        branch if branch and branch != "HEAD" else resolve_default_branch(repo=repo, runner=runner)
    )
    if target is None:
        return CommandResult(exit_code=_UNNAMEABLE_TARGET_EXIT, stdout="", stderr=_NO_TARGET_DETAIL)
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
