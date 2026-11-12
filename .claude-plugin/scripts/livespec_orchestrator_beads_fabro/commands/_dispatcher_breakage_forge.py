"""Cached forge reads and failure-log parsing for the breakage pass."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "FailedJob",
    "ScheduledRun",
    "failed_jobs",
    "job_evidence",
    "latest_completed_run",
    "workflow_api",
]

_CACHE_DURATION = "30m"
_GH_TIMEOUT_SECONDS = 30.0
_FAILURE_LINE = re.compile(r"[\w./-]+::[\w\[\]-]+")


@dataclass(frozen=True, kw_only=True)
class FailedJob:
    identifier: str
    name: str
    failing_step: str


@dataclass(frozen=True, kw_only=True)
class ScheduledRun:
    identifier: str
    conclusion: str
    head_sha: str
    url: str


def workflow_api(*, repo: Path, runner: CommandRunner, endpoint: str) -> CommandResult:
    return runner.run(
        argv=["gh", "api", "--cache", _CACHE_DURATION, endpoint],
        cwd=repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )


def latest_completed_run(*, result: CommandResult) -> ScheduledRun | str | None:
    payload = _json_object(result=result)
    runs = None if payload is None else payload.get("workflow_runs")
    if not isinstance(runs, list):
        return "workflow runs"
    if not runs:
        return None
    entry = runs[0] if isinstance(runs[0], dict) else {}
    fields = tuple(entry.get(key) for key in ("id", "conclusion", "head_sha", "html_url"))
    if not all(isinstance(field, str | int) and str(field) for field in fields):
        return "workflow run fields"
    return ScheduledRun(
        identifier=str(fields[0]), conclusion=str(fields[1]), head_sha=str(fields[2]), url=str(fields[3])
    )


def failed_jobs(*, result: CommandResult) -> tuple[FailedJob, ...] | str:
    payload = _json_object(result=result)
    jobs = None if payload is None else payload.get("jobs")
    if not isinstance(jobs, list):
        return "workflow jobs"
    found: list[FailedJob] = []
    for raw in jobs:
        if not isinstance(raw, dict) or raw.get("conclusion") != "failure":
            continue
        identifier, name = raw.get("id"), raw.get("name")
        if not isinstance(identifier, str | int) or not isinstance(name, str) or not name:
            return "workflow job fields"
        found.append(FailedJob(identifier=str(identifier), name=name, failing_step=_failed_step(job=raw)))
    return tuple(found)


def job_evidence(
    *, repo: Path, runner: CommandRunner, jobs: tuple[FailedJob, ...]
) -> tuple[tuple[str, ...], ...] | str:
    evidence: list[tuple[str, ...]] = []
    for job in jobs:
        result = workflow_api(
            repo=repo,
            runner=runner,
            endpoint=f"repos/{{owner}}/{{repo}}/actions/jobs/{job.identifier}/logs",
        )
        if result.exit_code != 0:
            return "workflow job log"
        evidence.append(_tests_in_log(text=result.stdout))
    return tuple(evidence)


def _tests_in_log(*, text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group(0)
            for line in text.splitlines()
            if "FAILED" in line
            for match in _FAILURE_LINE.finditer(line)
        )
    )


def _failed_step(*, job: dict[object, object]) -> str:
    steps = job.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and step.get("conclusion") == "failure":
                name = step.get("name")
                if isinstance(name, str) and name:
                    return name
    return "<unnamed failing step>"


def _json_object(*, result: CommandResult) -> dict[str, object] | None:
    if result.exit_code != 0:
        return None
    try:
        payload: object = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", payload) if isinstance(payload, dict) else None
