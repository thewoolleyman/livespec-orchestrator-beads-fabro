"""Tests for the Dispatcher post-merge AI acceptance pass."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    CriterionCheck,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    calls: list[tuple[list[str], Path, float]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = env
        self.calls.append((argv, cwd, timeout_seconds))
        return self.result


def _item(*, criteria: str | None) -> WorkItem:
    return WorkItem(
        id="bd-ib-test",
        type="task",
        status="active",
        title="Task",
        description="Do it.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria=criteria,
    )


def _outcome(
    *, status: str = "green", pr_number: int | None = 7, merge_sha: str | None = "abc123"
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-test",
        status=status,
        stage="done",
        pr_number=pr_number,
        merge_sha=merge_sha,
        detail="merged",
    )


def test_acceptance_pass_reads_diff_and_passes_when_criteria_have_evidence(
    tmp_path: Path,
) -> None:
    diff = "diff --git a/x b/x\n+verdict journaled telemetry watch\n+tests are green\n"
    runner = _Runner(result=CommandResult(exit_code=0, stdout=diff, stderr=""))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria="1. telemetry watch is journaled\n\n2. tests are green"),
        outcome=_outcome(),
        runner=runner,
    )

    assert result.verdict == "PASS"
    assert [call[0] for call in runner.calls] == [
        ["git", "show", "--format=", "--find-renames", "abc123"]
    ]
    record = result.journal_record(work_item_id="bd-ib-test", policy="ai-only")
    assert record["verdict"] == "PASS"
    assert record["diff"] == {
        "observed": True,
        "bytes": len(diff.encode()),
        "reason": "merged diff read",
    }
    assert record["telemetry"] == {
        "observed": True,
        "passed": True,
        "reason": "green merged dispatch with PR and merge sha",
    }


def test_acceptance_pass_fails_when_criteria_lack_diff_or_telemetry_evidence(
    tmp_path: Path,
) -> None:
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="diff --git a/x b/x\n+other\n", stderr="")
    )

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria="The release notes were updated."),
        outcome=_outcome(),
        runner=runner,
    )

    assert result.verdict == "FAIL"
    assert result.criteria == (
        CriterionCheck(
            text="The release notes were updated.",
            passed=False,
            reason="no merged diff or telemetry evidence",
        ),
    )


def test_acceptance_pass_treats_empty_diff_as_observed_input(tmp_path: Path) -> None:
    runner = _Runner(result=CommandResult(exit_code=0, stdout="\n", stderr=""))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria="Run the tests."),
        outcome=_outcome(),
        runner=runner,
    )

    assert result.verdict == "PASS"
    assert result.merged_diff == ""
    assert result.diff_reason == "merged diff is empty"
    assert result.criteria[0].reason == "matched green dispatch telemetry"


def test_acceptance_pass_fails_criteria_when_diff_is_unobservable(tmp_path: Path) -> None:
    runner = _Runner(result=CommandResult(exit_code=1, stdout="", stderr="fatal"))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria="The acceptance journal records the verdict."),
        outcome=_outcome(),
        runner=runner,
    )

    assert result.verdict == "FAIL"
    assert result.merged_diff is None
    assert result.diff_reason == "git show failed"


def test_acceptance_pass_no_criteria_passes_on_green_pr_without_merge_sha(tmp_path: Path) -> None:
    runner = _Runner(result=CommandResult(exit_code=0, stdout="ignored", stderr=""))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria=None),
        outcome=_outcome(merge_sha=None),
        runner=runner,
    )

    assert result.verdict == "PASS"
    assert result.criteria == ()
    assert result.diff_reason == "merge sha unavailable"
    assert result.telemetry_reason == "green merged dispatch with PR; merge sha unavailable"
    assert runner.calls == []


def test_acceptance_pass_fails_when_dispatch_telemetry_is_not_green(tmp_path: Path) -> None:
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="diff --git a/x b/x\n+verdict\n", stderr="")
    )

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria="verdict is journaled"),
        outcome=_outcome(status="failed"),
        runner=runner,
    )

    assert result.verdict == "FAIL"
    assert result.telemetry_reason == "dispatch outcome status was 'failed'"


def test_acceptance_pass_fails_when_pr_telemetry_is_missing(tmp_path: Path) -> None:
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="diff --git a/x b/x\n+verdict\n", stderr="")
    )

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(criteria="verdict is journaled"),
        outcome=_outcome(pr_number=None),
        runner=runner,
    )

    assert result.verdict == "FAIL"
    assert result.telemetry_reason == "merged PR number unavailable"
