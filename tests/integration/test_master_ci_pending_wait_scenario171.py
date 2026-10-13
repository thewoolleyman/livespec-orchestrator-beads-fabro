"""Binds `SPECIFICATION/scenarios.md` "Scenario 171 — A still-running master CI run makes the preflight wait, not refuse".

Driven through the REAL pre-dispatch gate — `step_discipline_refusal`, the one
sequence both dispatch paths reach — so each of the scenario's four outcomes is
read off the thing a dispatch actually consults: the gate's own return value
(refusal text, or None to proceed) and the records it appends to the dispatch
journal.

The clock and the sleep are the SHIPPED ones here, deliberately. The focused
tests in `tests/livespec_orchestrator_beads_fabro/commands/` inject a fake
clock, which is what makes the 1800-second bound and the 60-second ceiling
assertable at all; it also means those cases never execute the production
default. This tier shortens the poll INTERVAL instead of replacing the clock,
so the wait that runs here is the wait a dispatch runs, reached through a gate
that passes no seam and could not pass one.

Only two things are stood in: the gate's `CommandRunner` (the forge and git
reads) and the two wait figures. The classification, the deferral, the journal
and the gate's proceed/refuse decision are all production code.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_ci_preflight_wait,
    _dispatcher_step_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity

_BRANCH = "trunk"
_IS_WORKTREE = ("git", "rev-parse", "--is-inside-work-tree")
_ORIGIN_REFS = ("git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
_HEAD_SHORT = ("git", "rev-parse", "--short", "HEAD")
_HEAD_ANCESTOR = ("git", "merge-base", "--is-ancestor", "HEAD", f"origin/{_BRANCH}")
_ORIGIN_HEAD = ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
_RUN_LIST = (
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


@dataclass(kw_only=True)
class _Runner:
    """Argv-keyed stand-in whose `sequences` answer one argv differently per call.

    A runner that answered identically every time could not tell a preflight
    that re-read the default branch from one that read it once and cached, and
    that difference is the whole scenario.
    """

    results: dict[tuple[str, ...], CommandResult]
    sequences: dict[tuple[str, ...], list[CommandResult]] = field(default_factory=dict)
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
        key = tuple(argv)
        self.calls.append(key)
        queued = self.sequences.get(key)
        if queued:
            return queued.pop(0)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unscripted"))


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _run_list(*, status: str = "completed", database_id: int) -> CommandResult:
    return _ok(
        stdout=json.dumps([{"status": status, "conclusion": "success", "databaseId": database_id}])
    )


def _jobs(*, conclusion: str | None = "success", status: str = "completed") -> CommandResult:
    return _ok(
        stdout=json.dumps(
            {"jobs": [{"name": "ci-green", "conclusion": conclusion, "status": status}]}
        )
    )


def _jobs_argv(*, run_id: str) -> tuple[str, ...]:
    return ("gh", "run", "view", run_id, "--json", "jobs")


def _base_results() -> dict[tuple[str, ...], CommandResult]:
    """The reads every dispatch makes before the master-CI step is even reached."""
    return {
        _IS_WORKTREE: _ok(stdout="true\n"),
        _ORIGIN_REFS: _ok(stdout=f"origin/{_BRANCH}\n"),
        _HEAD_SHORT: _ok(stdout="abc1234\n"),
        _HEAD_ANCESTOR: _ok(),
        _ORIGIN_HEAD: _ok(stdout=f"origin/{_BRANCH}\n"),
        ("gh", "auth", "token"): _ok(stdout="secret\n"),
    }


def _gate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: _Runner, bound: float = 1800.0
) -> tuple[str | None, list[dict[str, object]]]:
    """Run the real pre-dispatch gate; return its decision and the journal it wrote."""
    monkeypatch.setattr(_dispatcher_ci_preflight_wait, "POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(_dispatcher_ci_preflight_wait, "WAIT_BOUND_SECONDS", bound)
    monkeypatch.setattr(_dispatcher_step_gate, "ShellCommandRunner", lambda: runner)
    journal = tmp_path / "journal.jsonl"
    refusal = _dispatcher_step_gate.step_discipline_refusal(
        args=argparse.Namespace(journal=str(journal)),
        repo=tmp_path,
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
    )
    records = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    return refusal, [record for record in records if record.get("step") == "master-ci"]


def test_scenario171_a_pending_run_that_concludes_green_lets_the_dispatch_proceed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _Runner(
        results={**_base_results(), _jobs_argv(run_id="404"): _jobs()},
        sequences={
            _RUN_LIST: [
                _run_list(status="in_progress", database_id=404),
                _run_list(database_id=404),
            ]
        },
    )

    refusal, records = _gate(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner)

    assert refusal is None
    assert [record["status"] for record in records] == ["passed"]
    assert records[0]["reason"] == "master-ci-green"
    assert records[0]["run_database_id"] == "404"


def test_scenario171_a_pending_run_that_concludes_red_refuses_as_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _Runner(
        results={**_base_results(), _jobs_argv(run_id="404"): _jobs(conclusion="failure")},
        sequences={
            _RUN_LIST: [
                _run_list(status="queued", database_id=404),
                _run_list(database_id=404),
            ]
        },
    )

    refusal, records = _gate(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner)

    assert refusal is not None
    assert "404" in refusal
    assert records[0]["reason"] == "master-ci-red"
    assert records[0]["status"] == "failed"
    assert records[0]["run_database_id"] == "404"


def test_scenario171_a_newer_run_replaces_the_one_being_waited_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first reading pends on run 404's OWN aggregate job, which is the point.

    A wait that narrowed to that job would conclude about 404 and never look at
    505, while still producing a perfectly ordinary pass. The journaled run id
    and the presence of 505's job lookup are what separate the two.
    """
    runner = _Runner(
        results={
            **_base_results(),
            _jobs_argv(run_id="404"): _jobs(status="in_progress"),
            _jobs_argv(run_id="505"): _jobs(),
        },
        sequences={
            _RUN_LIST: [_run_list(database_id=404), _run_list(database_id=505)],
        },
    )

    refusal, records = _gate(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner)

    assert refusal is None
    assert records[0]["reason"] == "master-ci-green"
    assert records[0]["run_database_id"] == "505"
    assert _jobs_argv(run_id="505") in runner.calls


def test_scenario171_a_run_still_pending_at_the_bound_is_deferred_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expiry: no dispatch, nothing claimed, and a record that says `deferred`.

    The gate refusing is what keeps the item unclaimed — every claim in both
    dispatch paths happens after this call returns — so the refusal and the
    `deferred` status are asserted as a PAIR. Either alone is satisfied by a
    wrong outcome: a proceed journaled `deferred` would start a dispatch
    against an unread default branch, and a refusal journaled `failed` is the
    exact report this scenario exists to retire.
    """
    runner = _Runner(
        results={**_base_results(), _RUN_LIST: _run_list(status="queued", database_id=606)}
    )

    refusal, records = _gate(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner, bound=0.0)

    assert refusal is not None
    assert records[0]["reason"] == "master-ci-pending"
    assert records[0]["status"] == "deferred"
    assert records[0]["run_database_id"] == "606"
    assert records[0]["pending_status"] == "queued"
    first_line = refusal.splitlines()[0]
    assert "still running" in first_line
    assert "has not failed" in first_line
    assert "ERROR" not in refusal
    assert "not proven green" not in refusal
    assert "master-health-restoration" not in refusal
    assert "recovery" not in records[0]
