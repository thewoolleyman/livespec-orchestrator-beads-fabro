"""Stale-cleanup janitor checks (the Dispatcher's janitor-check surface).

Re-homes the three stale-cleanup doctor checks livespec PR #403
retired from core per the v105 cross-boundary catalogue (coordinated
under livespec-impl-beads-e6x / livespec-5lup; source recoverable on
livespec master at the pre-deletion SHA 6d37dcaa under
`.claude-plugin/scripts/livespec/doctor/static/`, with paired tests
under `tests/livespec/doctor/static/`):

- `no-stale-merged-branch` — local branches whose tips are reachable
  from the default branch (`git branch -d` candidates). The default
  branch itself is excluded.
- `no-stale-merged-pr-branch` — remote branches fronted by a merged
  PR (`gh api -X DELETE repos/<owner>/<name>/git/refs/heads/<name>`
  candidates). The default branch is excluded.
- `no-stale-worktree` — secondary worktrees whose branch is either
  (a) merged into default, or (b) absent from the remote head set.
  Case (b) is load-bearing for the family's `gh pr merge --rebase`
  flow: a rebase-merge lands a DISTINCT SHA on default, so the merged
  branch never lists under `--merged`; its only durable cleanup
  signal is remote absence. The primary worktree is always excluded.

Every violation is severity `warn` (recoverable housekeeping,
mirroring the retired checks' warn-not-fail classification); a check
whose git / gh probes fail emits a single `skipped` finding instead.
All state is gathered through the engine's `CommandRunner` seam, so
the hermetic test tier scripts probe outputs without live git / gh /
Dolt access; the evaluations themselves are pure functions of the
gathered probe state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import LedgerFinding

__all__: list[str] = ["run_janitor_checks"]

_PROBE_TIMEOUT_SECONDS = 120.0
_WORKTREE_LINE_PREFIX = "worktree "
_BRANCH_LINE_PREFIX = "branch refs/heads/"
_HEADS_REF_PREFIX = "refs/heads/"
_JANITOR_CHECKS = (
    "no-stale-merged-branch",
    "no-stale-merged-pr-branch",
    "no-stale-worktree",
)


@dataclass(frozen=True, kw_only=True, slots=True)
class _Worktree:
    """One `git worktree list --porcelain` entry."""

    path: str
    branch: str | None
    is_primary: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class _ProbeState:
    """Everything the three evaluations need; None marks a failed probe."""

    default_branch: str
    merged: tuple[str, ...] | None
    remote_heads: tuple[str, ...] | None
    worktrees: tuple[_Worktree, ...] | None
    name_with_owner: str | None
    merged_pr_heads: tuple[str, ...] | None


def run_janitor_checks(*, repo: Path, runner: CommandRunner) -> list[LedgerFinding]:
    """Run the three stale-cleanup checks against the repo's git/gh state.

    Returns findings sorted by (check, item_id) so output is stable for
    journaling and tests. An empty list means there is no housekeeping
    to do (and no probe failed).
    """
    if _probe(runner=runner, repo=repo, argv=["git", "rev-parse", "--is-inside-work-tree"]) is None:
        return _all_skipped(reason=f"{repo} is not a git working tree")
    head_ref = _probe(
        runner=runner,
        repo=repo,
        argv=["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
    )
    if head_ref is None:
        return _all_skipped(reason="origin/HEAD is unset; default branch undetermined")
    default_branch = head_ref.strip().removeprefix("origin/")
    state = _gather(runner=runner, repo=repo, default_branch=default_branch)
    findings = [
        *_check_merged_branches(state=state),
        *_check_pr_branches(state=state),
        *_check_worktrees(state=state),
    ]
    return sorted(findings, key=lambda finding: (finding.check, finding.item_id))


def _gather(*, runner: CommandRunner, repo: Path, default_branch: str) -> _ProbeState:
    merged_raw = _probe(
        runner=runner,
        repo=repo,
        argv=[
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            "--merged",
            default_branch,
            "refs/heads",
        ],
    )
    remote_raw = _probe(runner=runner, repo=repo, argv=["git", "ls-remote", "--heads", "origin"])
    worktrees_raw = _probe(
        runner=runner,
        repo=repo,
        argv=["git", "worktree", "list", "--porcelain"],
    )
    nwo_raw = _probe(
        runner=runner,
        repo=repo,
        argv=["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
    )
    prs_raw = _probe(
        runner=runner,
        repo=repo,
        argv=[
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--json",
            "headRefName",
            "--jq",
            ".[].headRefName",
            "--limit",
            "100",
        ],
    )
    return _ProbeState(
        default_branch=default_branch,
        merged=_lines(raw=merged_raw),
        remote_heads=_parse_remote_heads(raw=remote_raw),
        worktrees=_parse_worktrees(raw=worktrees_raw),
        name_with_owner=None if nwo_raw is None else nwo_raw.strip(),
        merged_pr_heads=_lines(raw=prs_raw),
    )


def _check_merged_branches(*, state: _ProbeState) -> list[LedgerFinding]:
    if state.merged is None:
        return [_skipped(check="no-stale-merged-branch", reason="the merged-branch probe failed")]
    return [
        LedgerFinding(
            check="no-stale-merged-branch",
            item_id=name,
            severity="warn",
            message=(
                f"local branch is merged into `{state.default_branch}` and ready "
                f"to delete; corrective action: git branch -d {name}"
            ),
        )
        for name in sorted(state.merged)
        if name != state.default_branch
    ]


def _check_pr_branches(*, state: _ProbeState) -> list[LedgerFinding]:
    if state.remote_heads is None or state.name_with_owner is None or state.merged_pr_heads is None:
        return [
            _skipped(
                check="no-stale-merged-pr-branch",
                reason="a gh / ls-remote probe failed",
            )
        ]
    merged_set = set(state.merged_pr_heads)
    return [
        LedgerFinding(
            check="no-stale-merged-pr-branch",
            item_id=name,
            severity="warn",
            message=(
                f"remote branch is fronted by a merged PR and ready to delete; "
                f"corrective action: gh api -X DELETE "
                f"repos/{state.name_with_owner}/git/refs/heads/{name}"
            ),
        )
        for name in sorted(state.remote_heads)
        if name != state.default_branch and name in merged_set
    ]


def _check_worktrees(*, state: _ProbeState) -> list[LedgerFinding]:
    if state.merged is None or state.remote_heads is None or state.worktrees is None:
        return [
            _skipped(
                check="no-stale-worktree",
                reason="a git probe (merged / ls-remote / worktree list) failed",
            )
        ]
    return [
        LedgerFinding(
            check="no-stale-worktree",
            item_id=worktree.path,
            severity="warn",
            message=(
                f"secondary worktree on branch `{worktree.branch}` (merged into "
                f"`{state.default_branch}` or absent from the remote); "
                f"corrective action: git worktree remove {worktree.path}"
            ),
        )
        for worktree in state.worktrees
        if not worktree.is_primary
        and worktree.branch is not None
        and worktree.branch != state.default_branch
        and (worktree.branch in state.merged or worktree.branch not in state.remote_heads)
    ]


def _probe(*, runner: CommandRunner, repo: Path, argv: list[str]) -> str | None:
    """Run one probe; non-zero exit collapses to None (the skip signal)."""
    result = runner.run(argv=argv, cwd=repo, timeout_seconds=_PROBE_TIMEOUT_SECONDS)
    if result.exit_code != 0:
        return None
    return result.stdout


def _lines(*, raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def _parse_remote_heads(*, raw: str | None) -> tuple[str, ...] | None:
    """Parse `git ls-remote --heads origin` output into branch names."""
    if raw is None:
        return None
    heads: list[str] = []
    for line in raw.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith(_HEADS_REF_PREFIX):
            heads.append(ref[len(_HEADS_REF_PREFIX) :].strip())
    return tuple(heads)


def _parse_worktrees(*, raw: str | None) -> tuple[_Worktree, ...] | None:
    """Parse `git worktree list --porcelain` blocks; the first entry is primary."""
    if raw is None:
        return None
    entries: list[_Worktree] = []
    path: str | None = None
    branch: str | None = None
    for line in raw.splitlines():
        if line.startswith(_WORKTREE_LINE_PREFIX):
            if path is not None:
                entries.append(_Worktree(path=path, branch=branch, is_primary=len(entries) == 0))
            path = line[len(_WORKTREE_LINE_PREFIX) :]
            branch = None
        elif line.startswith(_BRANCH_LINE_PREFIX):
            branch = line[len(_BRANCH_LINE_PREFIX) :]
    if path is not None:
        entries.append(_Worktree(path=path, branch=branch, is_primary=len(entries) == 0))
    return tuple(entries)


def _skipped(*, check: str, reason: str) -> LedgerFinding:
    return LedgerFinding(
        check=check,
        item_id="-",
        severity="skipped",
        message=f"{reason}; check skipped",
    )


def _all_skipped(*, reason: str) -> list[LedgerFinding]:
    return [_skipped(check=check, reason=reason) for check in _JANITOR_CHECKS]
