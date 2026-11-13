"""Tests for the batched source-checkout containment probe."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_preflight import (
    source_checkout_preflight,
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


def test_source_preflight_batches_containment_and_prefers_the_default_ref(
    tmp_path: Path,
) -> None:
    """One containing-ref query chooses origin's default branch over another witness."""
    runner = _Runner(
        results={
            ("rev-parse", "--is-inside-work-tree"): _result(stdout="true\n"),
            ("rev-parse", "HEAD"): _result(stdout="abc123\n"),
            (
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/remotes/origin",
            ): _result(stdout="origin/feature\norigin/trunk\n"),
            ("merge-base", "--is-ancestor", "abc123", "origin/feature"): _result(exit_code=1),
            ("merge-base", "--is-ancestor", "abc123", "origin/trunk"): _result(),
            ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"): _result(
                stdout="origin/trunk\n"
            ),
            (
                "for-each-ref",
                "--contains",
                "abc123",
                "--format=%(refname:short)",
                "refs/remotes/origin",
            ): _result(stdout="origin/feature\norigin/trunk\n"),
        }
    )

    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)

    assert outcome.refusal is None
    assert outcome.record["origin_ref"] == "origin/trunk"
    assert not any(call[0] == "merge-base" for call in runner.calls)
    assert (
        runner.calls.count(
            (
                "for-each-ref",
                "--contains",
                "abc123",
                "--format=%(refname:short)",
                "refs/remotes/origin",
            )
        )
        == 1
    )


def test_source_preflight_checks_the_default_ref_before_scanning_all_origin_refs(
    tmp_path: Path,
) -> None:
    """A normal default-branch checkout avoids the all-refs ancestry walk."""
    runner = _Runner(
        results={
            ("rev-parse", "--is-inside-work-tree"): _result(stdout="true\n"),
            ("rev-parse", "HEAD"): _result(stdout="abc123\n"),
            (
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/remotes/origin",
            ): _result(stdout="origin/feature\norigin/trunk\n"),
            ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"): _result(
                stdout="origin/trunk\n"
            ),
            ("merge-base", "--is-ancestor", "abc123", "origin/trunk"): _result(),
            (
                "for-each-ref",
                "--contains",
                "abc123",
                "--format=%(refname:short)",
                "refs/remotes/origin",
            ): _result(stdout="origin/feature\norigin/trunk\n"),
        }
    )

    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)

    assert outcome.refusal is None
    assert outcome.record["origin_ref"] == "origin/trunk"
    assert ("merge-base", "--is-ancestor", "abc123", "origin/trunk") in runner.calls
    assert not any(call[:2] == ("for-each-ref", "--contains") for call in runner.calls)
