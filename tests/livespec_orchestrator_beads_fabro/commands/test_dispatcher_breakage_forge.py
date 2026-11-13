"""Focused coverage for cached forge parsing used by the breakage pass."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_breakage_pass as breakage_pass
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    FailedJob,
    ScheduledRun,
    failed_jobs,
    job_evidence,
    latest_completed_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_intake import (
    build_breakage_item,
    known_breakage_keys,
    template_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


def _result(*, payload: object, exit_code: int = 0) -> CommandResult:
    """Build a forge response without hiding the body under a test helper mock."""
    return CommandResult(exit_code=exit_code, stdout=json.dumps(payload), stderr="")


def test_forge_rejects_malformed_run_and_job_payloads() -> None:
    """The host cannot file from malformed forge data."""
    assert (
        latest_completed_run(result=_result(payload={"workflow_runs": [{}]}))
        == "workflow run fields"
    )
    assert (
        latest_completed_run(result=_result(payload={"workflow_runs": [0]}))
        == "workflow run fields"
    )
    assert latest_completed_run(result=_result(payload=[])) == "workflow runs"
    assert (
        latest_completed_run(result=CommandResult(exit_code=0, stdout="not json", stderr=""))
        == "workflow runs"
    )
    assert failed_jobs(result=_result(payload={"jobs": "not-a-list"})) == "workflow jobs"
    assert failed_jobs(result=_result(payload={"jobs": ["not-a-job"]})) == ()


class _LogRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, *, argv: list[str], **_: Any) -> CommandResult:
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="no test identifier", stderr="")


def test_forge_reads_empty_job_evidence_with_cached_gh_api() -> None:
    """A failed job without a test name retains its failing-step fallback."""
    jobs = failed_jobs(
        result=_result(
            payload={
                "jobs": [
                    {
                        "id": 1,
                        "name": "check",
                        "conclusion": "failure",
                        "steps": [0, {"name": None, "conclusion": "failure"}],
                    }
                ]
            }
        )
    )
    assert jobs == (FailedJob(identifier="1", name="check", failing_step="<unnamed failing step>"),)
    runner = _LogRunner()

    assert job_evidence(repo=Path(), runner=runner, jobs=jobs) == ((),)
    assert runner.calls[0][:4] == ["gh", "api", "--cache", "30m"]


def test_intake_shaping_keeps_deduplication_and_prose_guards_explicit() -> None:
    """Only persisted keys are reused, and generated prose remains safe."""
    assert known_breakage_keys(
        records=[
            {"id": "bd-known", "metadata": {"breakage_key": "key"}},
            {"id": 1, "metadata": {"breakage_key": "ignored"}},
            {"id": "bd-ignored", "metadata": None},
            {"id": "bd-nonstring", "metadata": {"breakage_key": 1}},
        ]
    ) == {"key": "bd-known"}
    item = build_breakage_item(
        item_id="bd-new",
        workflow="ci-root-uid.yml",
        job=FailedJob(identifier="7", name="check", failing_step="step"),
        run=ScheduledRun(identifier="42", conclusion="failure", head_sha="abc", url="https://run"),
        tests=(),
        captured_at="2026-11-13T00:00:00Z",
    )
    assert "No failing test named; failing step: step" in item.description
    assert template_refusal(description=item.description) is None
    assert template_refusal(description="{{ unsafe }}") == "template opener present: {{"


def test_pass_command_prints_timer_verdicts_and_rejects_bad_workflow_values(
    monkeypatch: Any,
) -> None:
    """The command wrapper journals every verdict and preserves invalid config as an error."""
    printed: list[str] = []
    original_pass = breakage_pass.breakage_pass
    monkeypatch.setattr(
        breakage_pass,
        "breakage_pass",
        lambda **_: breakage_pass.BreakagePassOutcome(exit_code=7, lines=("verdict",)),
    )
    monkeypatch.setattr(breakage_pass, "write_stdout", lambda *, text: printed.append(text))

    assert breakage_pass.run_breakage_pass_command(args=type("Args", (), {"repo": "."})()) == 7
    assert printed == ["verdict\n"]
    monkeypatch.setattr(breakage_pass, "breakage_pass", original_pass)
    monkeypatch.setattr(breakage_pass, "dispatcher_block", lambda **_: {"breakage_workflows": [1]})
    assert breakage_pass.breakage_pass(repo=Path(), runner=_LogRunner()).exit_code == 1


def test_behavior_runner_exposes_its_unexpected_endpoint_guard() -> None:
    """The scenario runner never silently accepts a forge endpoint it does not model."""
    from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_breakage_pass_behavior import (
        _Runner,
    )

    with pytest.raises(AssertionError):
        _Runner().run(argv=["gh", "api", "unknown"], cwd=Path(), timeout_seconds=1.0)
