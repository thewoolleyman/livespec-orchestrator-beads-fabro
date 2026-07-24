"""Focused tests for the dispatch source-checkout origin-reachability preflight."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_preflight import (
    source_checkout_preflight_refusal,
)


@dataclass(kw_only=True)
class _Runner:
    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        key = tuple(argv[1:])
        self.calls.append(key)
        return self.results[key]


def _result(*, exit_code: int = 0, stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _base_results() -> dict[tuple[str, ...], CommandResult]:
    return {
        ("rev-parse", "--is-inside-work-tree"): _result(stdout="true\n"),
        ("rev-parse", "--short", "HEAD"): _result(stdout="abc123\n"),
        ("rev-parse", "--abbrev-ref", "HEAD"): _result(stdout="master\n"),
        ("push", "--dry-run", "origin", "HEAD:master"): _result(
            exit_code=1,
            stderr="livespec: refusing commit/push at primary checkout; use a worktree\n",
        ),
    }


def test_source_preflight_fails_closed_when_origin_refs_are_unreadable(tmp_path: Path) -> None:
    """An unreadable origin-ref set is not treated as origin-reachable."""
    results = _base_results() | {
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            exit_code=128, stderr="bad origin\n"
        ),
        (
            "log",
            "--oneline",
            "--decorate",
            "--max-count=20",
            "HEAD",
            "--not",
            "--remotes=origin",
        ): _result(stdout="abc123 local commit\n"),
    }

    refusal = source_checkout_preflight_refusal(repo=tmp_path, runner=_Runner(results=results))

    assert refusal is not None
    assert refusal.record["origin_refs"] == []
    assert refusal.record["unpushed_commits"] == ["abc123 local commit"]


def test_source_preflight_names_unpushed_log_failure(tmp_path: Path) -> None:
    """If commit listing itself fails, the terminal refusal still carries that fact."""
    results = _base_results() | {
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            stdout="origin/master\n"
        ),
        ("merge-base", "--is-ancestor", "HEAD", "origin/master"): _result(exit_code=1),
        (
            "log",
            "--oneline",
            "--decorate",
            "--max-count=20",
            "HEAD",
            "--not",
            "--remotes=origin",
        ): _result(exit_code=128, stderr="cannot enumerate\n"),
    }

    refusal = source_checkout_preflight_refusal(repo=tmp_path, runner=_Runner(results=results))

    assert refusal is not None
    assert refusal.record["unpushed_commits"] == [
        "<unable to list unpushed commits: cannot enumerate>"
    ]
    assert "cannot enumerate" in refusal.detail
