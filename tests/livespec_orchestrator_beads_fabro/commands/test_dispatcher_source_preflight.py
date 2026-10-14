"""Focused tests for the dispatch source-checkout origin-reachability preflight."""

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


def _base_results() -> dict[tuple[str, ...], CommandResult]:
    return {
        ("rev-parse", "--is-inside-work-tree"): _result(stdout="true\n"),
        ("rev-parse", "HEAD"): _result(stdout="abc123\n"),
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

    outcome = source_checkout_preflight(repo=tmp_path, runner=_Runner(results=results))

    assert outcome.refusal is not None
    assert outcome.record["origin_refs"] == []
    assert outcome.record["unpushed_commits"] == ["abc123 local commit"]


def test_source_preflight_names_unpushed_log_failure(tmp_path: Path) -> None:
    """If commit listing itself fails, the terminal refusal still carries that fact."""
    results = _base_results() | {
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            stdout="origin/master\n"
        ),
        ("merge-base", "--is-ancestor", "abc123", "origin/master"): _result(exit_code=1),
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

    outcome = source_checkout_preflight(repo=tmp_path, runner=_Runner(results=results))

    assert outcome.refusal is not None
    assert outcome.record["unpushed_commits"] == [
        "<unable to list unpushed commits: cannot enumerate>"
    ]
    assert "cannot enumerate" in outcome.refusal.detail


def test_source_preflight_reports_no_unpushed_commits_when_the_log_is_empty(
    tmp_path: Path,
) -> None:
    """An empty unpushed log still refuses, and says the reachability check failed anyway."""
    results = _base_results() | {
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            stdout="origin/HEAD\norigin/master\n"
        ),
        ("merge-base", "--is-ancestor", "abc123", "origin/master"): _result(exit_code=1),
        (
            "log",
            "--oneline",
            "--decorate",
            "--max-count=20",
            "HEAD",
            "--not",
            "--remotes=origin",
        ): _result(stdout=""),
    }

    outcome = source_checkout_preflight(repo=tmp_path, runner=_Runner(results=results))

    assert outcome.refusal is not None
    assert outcome.record["unpushed_commits"] == [
        "<no unpushed commits listed; origin reachability still failed>"
    ]


def test_source_preflight_journals_a_pass_carrying_the_step_identifier(tmp_path: Path) -> None:
    """An origin-reachable HEAD is a sanctioned outcome with its own record."""
    results = _base_results() | {
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            stdout="origin/master\n"
        ),
        ("merge-base", "--is-ancestor", "abc123", "origin/master"): _result(),
    }

    outcome = source_checkout_preflight(repo=tmp_path, runner=_Runner(results=results))

    assert outcome.refusal is None
    assert outcome.record["step"] == "source-checkout"
    assert outcome.record["status"] == "passed"
    assert outcome.record["reason"] == "source-head-origin-reachable"
    assert outcome.record["head"] == "abc123"
    assert outcome.record["origin_refs"] == ["origin/master"]


def test_source_preflight_refuses_a_target_that_is_not_a_git_worktree(tmp_path: Path) -> None:
    """Absence of proof is refusal: an unverifiable target never proceeds silently."""
    results = {
        ("rev-parse", "--is-inside-work-tree"): _result(exit_code=128, stderr="not a repo\n"),
    }
    runner = _Runner(results=results)

    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert outcome.record["step"] == "source-checkout"
    assert outcome.record["reason"] == "source-checkout-not-a-git-worktree"
    assert outcome.record["repo"] == str(tmp_path)
    assert "not a Git worktree" in outcome.refusal.detail
    assert "dispatcher.step_waivers" in outcome.refusal.detail
    # No further git read is attempted: the step already knows it cannot answer.
    assert runner.calls == [("rev-parse", "--is-inside-work-tree")]


def test_source_preflight_head_is_unknown_when_rev_parse_fails(tmp_path: Path) -> None:
    """A HEAD the checkout will not name still refuses, rendering the unknown marker."""
    results = _base_results() | {
        ("rev-parse", "HEAD"): _result(exit_code=128, stderr="no HEAD\n"),
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(stdout=""),
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

    outcome = source_checkout_preflight(repo=tmp_path, runner=_Runner(results=results))

    assert outcome.refusal is not None
    assert "HEAD: <unknown>" in outcome.refusal.detail


def test_source_preflight_pushes_the_dry_run_to_the_resolved_default_branch(
    tmp_path: Path,
) -> None:
    """A detached HEAD names no branch, so the dry-run targets the RESOLVED one.

    `trunk` is deliberately a branch name this fleet would never have hardcoded:
    a target that agreed with the retired constant could not tell a resolution
    apart from a literal that happens to match.
    """
    results = _detached_head_results() | {
        ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"): _result(stdout="origin/trunk\n"),
        ("push", "--dry-run", "origin", "HEAD:trunk"): _result(exit_code=1, stderr="refused\n"),
    }
    runner = _Runner(results=results)

    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert ("push", "--dry-run", "origin", "HEAD:trunk") in runner.calls
    assert not any(call[:1] == ("push",) and "HEAD:master" in call for call in runner.calls)


def test_source_preflight_pushes_nothing_when_no_default_branch_can_be_named(
    tmp_path: Path,
) -> None:
    """Both routes silent on a detached HEAD: the outcome SAYS so instead of guessing."""
    results = _detached_head_results() | {
        ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"): _result(exit_code=128),
        ("repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"): _result(
            exit_code=1, stderr="no gh credential\n"
        ),
    }
    runner = _Runner(results=results)

    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert not any(call[:1] == ("push",) for call in runner.calls)
    assert "no branch to dry-run a push at" in outcome.refusal.detail


def _detached_head_results() -> dict[tuple[str, ...], CommandResult]:
    """An unreachable HEAD with no branch of its own, ready for a per-case push arm."""
    return _base_results() | {
        ("rev-parse", "--abbrev-ref", "HEAD"): _result(stdout="HEAD\n"),
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(stdout=""),
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


def test_preflight_records_the_ref_that_actually_contains_the_pinned_source_head(
    *, tmp_path: Path
) -> None:
    results = _base_results() | {
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            stdout="origin/unrelated\norigin/containing\n"
        ),
        ("merge-base", "--is-ancestor", "abc123", "origin/unrelated"): _result(exit_code=1),
        ("merge-base", "--is-ancestor", "abc123", "origin/containing"): _result(),
    }
    runner = _Runner(results=results)
    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)
    assert outcome.refusal is None
    assert outcome.record["origin_ref"] == "origin/containing"
    assert outcome.record["origin_refs"] == ["origin/unrelated", "origin/containing"]
    assert ("merge-base", "--is-ancestor", "abc123", "origin/containing") in runner.calls


def test_unreadable_head_cannot_produce_an_unpinned_containment_witness(*, tmp_path: Path) -> None:
    results = _detached_head_results() | {
        ("rev-parse", "HEAD"): _result(exit_code=128),
        ("rev-parse", "--abbrev-ref", "HEAD"): _result(stdout="master\n"),
        ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): _result(
            stdout="origin/master\n"
        ),
    }
    runner = _Runner(results=results)
    outcome = source_checkout_preflight(repo=tmp_path, runner=runner)
    assert outcome.refusal is not None
    assert not any(call[0] == "merge-base" for call in runner.calls)
    assert "HEAD: <unknown>" in outcome.refusal.detail
