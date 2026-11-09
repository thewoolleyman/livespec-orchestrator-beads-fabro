"""A latest master-CI run that carries no verdict walks back instead of refusing.

Scenario 171: a run whose aggregate job is missing, or concluded cancelled,
skipped or startup_failure, is a run with NO verdict. It is classified once, in
one place, and handled exactly as a still-pending latest run is.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_ci_preflight as preflight
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    MasterCiOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_wait import MasterCiWait
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_BRANCH = "trunk"
_ORIGIN_HEAD = ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
_LATEST_LIST = (
    "gh",
    "run",
    "list",
    "--branch",
    _BRANCH,
    "--limit",
    "1",
    "--workflow",
    "CI",
    "--json",
    "status,conclusion,databaseId",
)
_RECENT_LIST = (
    "gh",
    "run",
    "list",
    "--branch",
    _BRANCH,
    "--limit",
    "100",
    "--workflow",
    "CI",
    "--json",
    "databaseId,headSha,status,conclusion,createdAt",
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
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unscripted"))


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _jobs_argv(*, run_id: str) -> tuple[str, ...]:
    return ("gh", "run", "view", run_id, "--json", "jobs")


def _jobs(*, conclusion: str | None) -> CommandResult:
    jobs: list[dict[str, str]] = [{"name": "export-telemetry", "conclusion": "failure"}]
    if conclusion is not None:
        jobs.append({"name": "ci-green", "conclusion": conclusion, "status": "completed"})
    return _ok(stdout=json.dumps({"jobs": jobs}))


def _recent(*, ids_and_heads: list[tuple[int, str]]) -> CommandResult:
    runs = [
        {
            "databaseId": run_id,
            "headSha": head,
            "status": "completed",
            "conclusion": "success",
            "createdAt": f"2026-11-09T1{index}:00:00Z",
        }
        for index, (run_id, head) in zip(range(9, 0, -1), ids_and_heads, strict=False)
    ]
    return _ok(stdout=json.dumps(runs))


def _scenario(
    *,
    latest: str | None,
    older: dict[str, str | None],
    compare: str = "ahead",
) -> _Runner:
    """A latest run 303 beside older runs 202 (newer) and 101, keyed by job conclusion."""
    heads = {"202": "head-202", "101": "head-101"}
    results: dict[tuple[str, ...], CommandResult] = {
        _ORIGIN_HEAD: _ok(stdout=f"origin/{_BRANCH}\n"),
        _LATEST_LIST: _ok(
            stdout=json.dumps([{"status": "completed", "conclusion": "failure", "databaseId": 303}])
        ),
        _RECENT_LIST: _recent(
            ids_and_heads=[(303, "head-303"), *[(int(rid), heads[rid]) for rid in older]]
        ),
        _jobs_argv(run_id="303"): _jobs(conclusion=latest),
    }
    for run_id, conclusion in older.items():
        results[_jobs_argv(run_id=run_id)] = _jobs(conclusion=conclusion)
        results[
            (
                "gh",
                "api",
                f"repos/{{owner}}/{{repo}}/compare/{heads[run_id]}...{_BRANCH}",
                "--jq",
                ".status",
            )
        ] = _ok(stdout=compare)
    return _Runner(results=results)


def _preflight(*, tmp_path: Path, runner: _Runner) -> MasterCiOutcome:
    wait = MasterCiWait(
        now=lambda: 0.0, sleep=lambda _seconds: None, progress=io.StringIO(), bound_seconds=0.0
    )
    return preflight.master_ci_preflight(repo=tmp_path, runner=runner, wait=wait)


_NO_VERDICT_LATEST = [
    pytest.param(None, "is missing from run 303", id="missing-job"),
    pytest.param("cancelled", "`cancelled`", id="cancelled"),
    pytest.param("skipped", "`skipped`", id="skipped"),
    pytest.param("startup_failure", "`startup_failure`", id="startup-failure"),
]


@pytest.mark.parametrize(("latest", "reason_fragment"), _NO_VERDICT_LATEST)
def test_a_no_verdict_latest_run_passes_on_the_newest_green_ancestor(
    tmp_path: Path, latest: str | None, reason_fragment: str
) -> None:
    runner = _scenario(latest=latest, older={"202": None, "101": "success"})

    outcome = _preflight(tmp_path=tmp_path, runner=runner)

    assert outcome.refusal is None
    record = outcome.record
    assert record["status"] == "passed"
    assert record["run_database_id"] == "101"
    assert record["head_sha"] == "head-101"
    assert record["no_verdict_run_database_id"] == "303"
    assert reason_fragment in str(record["no_verdict_reason"])
    assert "303" in str(record["detail"])
    assert "101" in str(record["detail"])
    assert "head-101" in str(record["detail"])


@pytest.mark.parametrize("older", ["cancelled", "skipped", "startup_failure"])
def test_a_no_verdict_older_run_is_walked_past_not_read_as_red(tmp_path: Path, older: str) -> None:
    runner = _scenario(latest="cancelled", older={"202": older, "101": "success"})

    outcome = _preflight(tmp_path=tmp_path, runner=runner)

    assert outcome.refusal is None
    assert outcome.record["run_database_id"] == "101"


def test_a_no_verdict_latest_run_refuses_on_a_newer_red_verdict_behind_it(
    tmp_path: Path,
) -> None:
    runner = _scenario(latest=None, older={"202": "failure", "101": "success"})

    outcome = _preflight(tmp_path=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert outcome.record["reason"] == "master-ci-red"
    assert outcome.record["run_database_id"] == "202"


def test_no_verdict_on_any_run_waits_on_the_latest_run_instead_of_refusing(
    tmp_path: Path,
) -> None:
    runner = _scenario(latest=None, older={"202": "cancelled", "101": None})

    outcome = _preflight(tmp_path=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert outcome.record["reason"] == "master-ci-pending"
    assert outcome.record["status"] == "deferred"
    assert outcome.record["run_database_id"] == "303"
    assert "is missing" not in str(outcome.refusal.detail)


def test_a_green_verdict_that_is_not_an_ancestor_waits_instead_of_passing(
    tmp_path: Path,
) -> None:
    runner = _scenario(latest="cancelled", older={"101": "success"}, compare="behind")

    outcome = _preflight(tmp_path=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert outcome.record["reason"] == "master-ci-pending"
