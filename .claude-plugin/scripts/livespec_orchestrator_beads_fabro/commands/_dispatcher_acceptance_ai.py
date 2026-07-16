"""Post-merge AI acceptance pass for Dispatcher completions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "AcceptancePassResult",
    "CriterionCheck",
    "run_acceptance_pass",
]

_DIFF_TIMEOUT_SECONDS = 30.0
_EXTERNAL_VERIFICATION_TERMS = frozenset(
    {
        "check",
        "checks",
        "green",
        "test",
        "tests",
        "verify",
        "verified",
        "verification",
        "validation",
    }
)
_STOP_WORDS = frozenset(
    {
        "acceptance",
        "against",
        "branch",
        "computed",
        "criteria",
        "criterion",
        "direction",
        "effective",
        "either",
        "every",
        "field",
        "human",
        "item",
        "journaled",
        "minimum",
        "mode",
        "policy",
        "produces",
        "records",
        "status",
        "their",
        "under",
        "verdict",
        "work",
    }
)


@dataclass(frozen=True, kw_only=True)
class CriterionCheck:
    """One acceptance criterion's deterministic read-and-judge result."""

    text: str
    passed: bool
    reason: str

    def as_record(self) -> dict[str, object]:
        return {"text": self.text, "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True, kw_only=True)
class AcceptancePassResult:
    """The post-merge acceptance verdict and the inputs that produced it."""

    verdict: str
    merged_diff: str | None
    diff_reason: str
    telemetry_passed: bool
    telemetry_reason: str
    criteria: tuple[CriterionCheck, ...]

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
            "diff": {
                "observed": self.merged_diff is not None,
                "bytes": 0 if self.merged_diff is None else len(self.merged_diff.encode()),
                "reason": self.diff_reason,
            },
            "criteria": {
                "observed": bool(self.criteria),
                "checks": [check.as_record() for check in self.criteria],
            },
            "telemetry": {
                "observed": True,
                "passed": self.telemetry_passed,
                "reason": self.telemetry_reason,
            },
        }


def run_acceptance_pass(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    runner: CommandRunner | None = None,
) -> AcceptancePassResult:
    """Read the merged diff, judge criteria, watch telemetry, and return PASS/FAIL."""
    active_runner = ShellCommandRunner() if runner is None else runner
    diff_result = _read_merged_diff(repo=repo, outcome=outcome, runner=active_runner)
    telemetry_passed, telemetry_reason = _telemetry_verdict(outcome=outcome)
    checks = _criteria_checks(
        criteria_text=item.acceptance_criteria,
        merged_diff=diff_result.merged_diff,
        telemetry_passed=telemetry_passed,
    )
    verdict = (
        "PASS" if _passes(diff=diff_result, telemetry=telemetry_passed, checks=checks) else "FAIL"
    )
    return AcceptancePassResult(
        verdict=verdict,
        merged_diff=diff_result.merged_diff,
        diff_reason=diff_result.reason,
        telemetry_passed=telemetry_passed,
        telemetry_reason=telemetry_reason,
        criteria=checks,
    )


@dataclass(frozen=True, kw_only=True)
class _DiffResult:
    merged_diff: str | None
    reason: str


def _read_merged_diff(
    *, repo: Path, outcome: DispatchOutcome, runner: CommandRunner
) -> _DiffResult:
    merge_sha = outcome.merge_sha
    if merge_sha is None:
        return _DiffResult(merged_diff=None, reason="merge sha unavailable")
    result = runner.run(
        argv=["git", "show", "--format=", "--find-renames", merge_sha],
        cwd=repo,
        timeout_seconds=_DIFF_TIMEOUT_SECONDS,
    )
    return _diff_from_command(result=result)


def _diff_from_command(*, result: CommandResult) -> _DiffResult:
    if result.exit_code != 0:
        return _DiffResult(merged_diff=None, reason="git show failed")
    if not result.stdout.strip():
        return _DiffResult(merged_diff="", reason="merged diff is empty")
    return _DiffResult(merged_diff=result.stdout, reason="merged diff read")


def _telemetry_verdict(*, outcome: DispatchOutcome) -> tuple[bool, str]:
    if outcome.status != "green":
        return False, f"dispatch outcome status was {outcome.status!r}"
    if outcome.pr_number is None:
        return False, "merged PR number unavailable"
    if outcome.merge_sha is None:
        return True, "green merged dispatch with PR; merge sha unavailable"
    return True, "green merged dispatch with PR and merge sha"


def _criteria_checks(
    *, criteria_text: str | None, merged_diff: str | None, telemetry_passed: bool
) -> tuple[CriterionCheck, ...]:
    criteria = _criteria_lines(criteria_text=criteria_text)
    if not criteria:
        return ()
    normalized_diff = "" if merged_diff is None else merged_diff.lower()
    return tuple(
        _judge_criterion(
            criterion=criterion,
            normalized_diff=normalized_diff,
            telemetry_passed=telemetry_passed,
        )
        for criterion in criteria
    )


def _criteria_lines(*, criteria_text: str | None) -> tuple[str, ...]:
    if criteria_text is None:
        return ()
    lines: list[str] = []
    for raw in criteria_text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw).strip()
        if line:
            lines.append(line)
    return tuple(lines)


def _judge_criterion(
    *, criterion: str, normalized_diff: str, telemetry_passed: bool
) -> CriterionCheck:
    terms = _significant_terms(text=criterion)
    if any(term in normalized_diff for term in terms):
        return CriterionCheck(text=criterion, passed=True, reason="matched merged diff evidence")
    if telemetry_passed and any(term in _EXTERNAL_VERIFICATION_TERMS for term in terms):
        return CriterionCheck(
            text=criterion, passed=True, reason="matched green dispatch telemetry"
        )
    return CriterionCheck(
        text=criterion, passed=False, reason="no merged diff or telemetry evidence"
    )


def _significant_terms(*, text: str) -> tuple[str, ...]:
    terms: list[str] = []
    for term in re.findall(r"[a-z0-9_]{4,}", text.lower()):
        if term not in _STOP_WORDS:
            terms.append(term)
    return tuple(terms)


def _passes(*, diff: _DiffResult, telemetry: bool, checks: tuple[CriterionCheck, ...]) -> bool:
    if not telemetry:
        return False
    if checks:
        return diff.merged_diff is not None and all(check.passed for check in checks)
    return True
