"""Validate that a seeded recovery keeps its preserved work through publication.

A seed is an invariant of a factory command path, not a suggestion to an agent.
The initial checkout establishes it, while each later settled commit and the
pre-rebase publication head must still descend from the latest accepted
reference. A complete carried patch is the narrow exception: it advances the
reference because an agent may reconstruct the preserved change on another
lineage, but a partial reconstruction fails before a later command can hide it.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner

__all__: list[str] = [
    "LineageCheck",
    "check_prepare",
    "check_publish",
    "check_refresh",
    "check_settle",
    "main",
]

_SEED_ENV = "LIVESPEC_SEEDED_LINEAGE_SEED"
_WORK_ITEM_ENV = "LIVESPEC_WORK_ITEM_ID"
_STATE_NAME = "livespec-seeded-lineage-reference"
_CONTENT_CARRIED_MARKER = "livespec-seeded-lineage-content-carried"


@dataclass(frozen=True, kw_only=True)
class LineageCheck:
    """The result of one seed-lineage boundary check."""

    ok: bool
    cause: str
    next_expected: str
    carried: bool = False


def check_prepare(
    *, repo: Path, seed: str, head: str, runner: CommandRunner | None = None
) -> LineageCheck:
    """Refuse before implement unless the prepared head descends from the seed."""
    if _is_ancestor(repo=repo, ancestor=seed, descendant=head, runner=runner):
        return LineageCheck(ok=True, cause="", next_expected=seed)
    return LineageCheck(
        ok=False,
        cause=(
            "LIVESPEC_SEEDED_LINEAGE_PREPARE_REFUSED: recovery seed "
            f"{seed} is not an ancestor of checked-out head {head}"
        ),
        next_expected=seed,
    )


def check_settle(
    *, repo: Path, expected: str, settled: str, runner: CommandRunner | None = None
) -> LineageCheck:
    """Accept ancestry or a whole carried patch, advancing only on that exception."""
    if _is_ancestor(repo=repo, ancestor=expected, descendant=settled, runner=runner):
        return LineageCheck(ok=True, cause="", next_expected=expected)
    missing = _first_unborne_change(repo=repo, expected=expected, settled=settled, runner=runner)
    if missing is None:
        return LineageCheck(
            ok=True,
            cause=(
                "LIVESPEC_SEEDED_LINEAGE_CONTENT_CARRIED: broken lineage; seed "
                f"{expected} content carried by settled commit {settled}"
            ),
            next_expected=settled,
            carried=True,
        )
    return LineageCheck(
        ok=False,
        cause=(
            "LIVESPEC_SEEDED_LINEAGE_SETTLE_REFUSED: expected commit "
            f"{expected}, settled commit {settled}, first seed change it lacks: {missing}"
        ),
        next_expected=expected,
    )


def check_publish(
    *, repo: Path, expected: str, tip: str, runner: CommandRunner | None = None
) -> LineageCheck:
    """Refuse publication before its rebase when the current tip dropped lineage."""
    if _is_ancestor(repo=repo, ancestor=expected, descendant=tip, runner=runner):
        return LineageCheck(ok=True, cause="", next_expected=expected)
    return LineageCheck(
        ok=False,
        cause=(
            "LIVESPEC_SEEDED_LINEAGE_PUBLISH_REFUSED: expected commit "
            f"{expected} is not an ancestor of branch tip {tip}"
        ),
        next_expected=expected,
    )


def check_refresh(
    *,
    repo: Path,
    expected: str,
    before_refresh: str,
    refreshed: str,
    runner: CommandRunner | None = None,
) -> LineageCheck:
    """Advance only after a command refresh began from accepted lineage."""
    if not _is_ancestor(
        repo=repo,
        ancestor=expected,
        descendant=before_refresh,
        runner=runner,
    ):
        return LineageCheck(
            ok=False,
            cause=(
                "LIVESPEC_SEEDED_LINEAGE_REFRESH_REFUSED: expected commit "
                f"{expected} is not an ancestor of pre-refresh head {before_refresh}"
            ),
            next_expected=expected,
        )
    return LineageCheck(
        ok=True,
        cause="",
        next_expected=expected if before_refresh == refreshed else refreshed,
    )


def main(*, argv: list[str] | None = None) -> int:
    """Run one command-node boundary check when this run was seeded.

    The state lives under Git's private directory, so it survives engine
    checkpoints but never enters the work tree an agent can accidentally commit.
    """
    parser = argparse.ArgumentParser()
    _boundary = parser.add_argument("boundary", choices=("prepare", "refresh", "settle", "publish"))
    parsed = parser.parse_args(argv)
    seed = os.environ.get(_SEED_ENV, "")
    if not seed:
        return 0
    repo = Path.cwd()
    state = _git_dir(repo=repo) / _STATE_NAME
    head = _git(repo=repo, args=("rev-parse", "HEAD"), runner=None)
    initial = parsed.boundary == "prepare"
    expected = seed if initial else state.read_text(encoding="utf-8").strip()
    result = _check_boundary(
        repo=repo,
        boundary=parsed.boundary,
        expected=expected,
        head=head,
    )
    if result.carried:
        _record_carried_content(repo=repo, seed=expected, settled=head)
    if result.ok and (initial or result.next_expected != expected):
        bytes_written = state.write_text(f"{result.next_expected}\n", encoding="utf-8")
        _ = bytes_written
    if result.cause:
        _ = sys.stderr.write(result.cause + "\n")
    return 0 if result.ok else 1


def _check_boundary(*, repo: Path, boundary: str, expected: str, head: str) -> LineageCheck:
    """Check the line of descent appropriate to one command boundary."""
    if boundary == "prepare":
        return check_prepare(repo=repo, seed=expected, head=head)
    if boundary == "settle":
        return check_settle(repo=repo, expected=expected, settled=head)
    if boundary == "publish":
        return check_publish(repo=repo, expected=expected, tip=head)
    before_refresh = os.environ.get("LIVESPEC_SEEDED_LINEAGE_REFRESH_BEFORE", "")
    if not before_refresh:
        return LineageCheck(
            ok=False,
            cause=(
                "LIVESPEC_SEEDED_LINEAGE_REFRESH_REFUSED: refresh did not name "
                "its pre-refresh head"
            ),
            next_expected=expected,
        )
    return check_refresh(
        repo=repo,
        expected=expected,
        before_refresh=before_refresh,
        refreshed=head,
    )


def _record_carried_content(*, repo: Path, seed: str, settled: str) -> None:
    """Append the durable account required when content, rather than ancestry, passes."""
    work_item_id = os.environ.get(_WORK_ITEM_ENV)
    if work_item_id is None:
        return
    body = "\n".join(
        (
            _CONTENT_CARRIED_MARKER,
            "",
            f"seed commit: {seed}",
            f"settled commit: {settled}",
            "broken lineage with seed content carried",
        )
    )
    append_work_item_comment(
        path=store_config(repo=repo),
        work_item_id=work_item_id,
        body=body,
    )


def _is_ancestor(
    *, repo: Path, ancestor: str, descendant: str, runner: CommandRunner | None
) -> bool:
    """Whether `ancestor` is a Git ancestor of `descendant`."""
    result = _run(
        repo=repo,
        args=("merge-base", "--is-ancestor", ancestor, descendant),
        runner=runner,
        permits_nonzero=True,
    )
    if result.exit_code in (0, 1):
        return result.exit_code == 0
    raise RuntimeError(result.stderr.strip() or "git merge-base could not compare lineage")


def _first_unborne_change(
    *, repo: Path, expected: str, settled: str, runner: CommandRunner | None
) -> str | None:
    """The first seed line absent from, or restored by, the settled tree."""
    base = _git(repo=repo, args=("merge-base", expected, settled), runner=runner)
    files = _git_lines(
        repo=repo,
        args=("diff", "--name-only", base, expected),
        runner=runner,
    )
    for path in files:
        settled_lines = _file_lines(repo=repo, commit=settled, path=path, runner=runner)
        diff_lines = _git_lines(
            repo=repo,
            args=("diff", "--unified=0", base, expected, "--", path),
            runner=runner,
        )
        for line in diff_lines:
            if line.startswith(("+++", "---")):
                continue
            if line.startswith("+") and line[1:] not in settled_lines:
                return f"{path}: added line {line[1:]!r}"
            if line.startswith("-") and line[1:] in settled_lines:
                return f"{path}: removed line {line[1:]!r} remains"
    return None


def _file_lines(
    *, repo: Path, commit: str, path: str, runner: CommandRunner | None
) -> frozenset[str]:
    """The text lines of one path at one commit, or no lines when it is absent."""
    result = _run(
        repo=repo,
        args=("show", f"{commit}:{path}"),
        runner=runner,
        permits_nonzero=True,
    )
    if result.exit_code == 0:
        return frozenset(result.stdout.splitlines())
    return frozenset()


def _git(*, repo: Path, args: tuple[str, ...], runner: CommandRunner | None) -> str:
    """Run one Git read that must succeed."""
    return _run(repo=repo, args=args, runner=runner, permits_nonzero=False).stdout.strip()


def _git_lines(
    *, repo: Path, args: tuple[str, ...], runner: CommandRunner | None
) -> tuple[str, ...]:
    """Run one Git read and preserve its line-oriented answer."""
    return tuple(
        line
        for line in _run(
            repo=repo,
            args=args,
            runner=runner,
            permits_nonzero=False,
        ).stdout.splitlines()
        if line
    )


def _run(
    *, repo: Path, args: tuple[str, ...], runner: CommandRunner | None, permits_nonzero: bool
) -> CommandResult:
    """Execute one checked Git read and return stdout."""
    result = (ShellCommandRunner() if runner is None else runner).run(
        argv=["git", *args], cwd=repo, timeout_seconds=30.0
    )
    if not permits_nonzero and result.exit_code != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result


def _git_dir(*, repo: Path) -> Path:
    """Resolve this worktree's private Git directory."""
    return Path(_git(repo=repo, args=("rev-parse", "--git-path", "."), runner=None))
