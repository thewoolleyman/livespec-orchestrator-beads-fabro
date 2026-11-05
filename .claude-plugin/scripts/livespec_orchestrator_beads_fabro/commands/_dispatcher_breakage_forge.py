"""Cached GitHub reads and response parsing for the breakage pass."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = ["FailedJob", "Run", "failed_jobs", "latest_completed_run"]

_CACHE_DURATION = "30m"
_GH_TIMEOUT_SECONDS = 60
_TEST_FAILURE_RE = re.compile(
    r"(?m)^(?:\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+)?(?:FAILED|ERROR)\s+([^\s].*?)(?:\s+-\s+.*)?$"
)


@dataclass(frozen=True, kw_only=True)
class Run:
    """The completed workflow run relevant to one capture pass."""

    identifier: int
    conclusion: str
    head_sha: str
    url: str


@dataclass(frozen=True, kw_only=True)
class FailedJob:
    """A failed job and its best available human-readable failure detail."""

    identifier: int
    name: str
    failed_step: str


def latest_completed_run(  # noqa: PLR0911 - each malformed response gets its own verdict.
    *, repo: Path, workflow: str
) -> tuple[Run | None, str | None]:
    """Read the latest completed default-branch workflow run through gh's cache."""
    default_branch, problem = _cached_json(repo=repo, endpoint="repos/{owner}/{repo}")
    if problem is not None:
        return None, f"default branch: {problem}"
    if default_branch is None:
        return None, "default branch: malformed response"
    branch = _string(value=default_branch, key="default_branch")
    if branch is None:
        return None, "default branch: response omitted default_branch"
    response, problem = _cached_json(
        repo=repo,
        endpoint=(
            f"repos/{{owner}}/{{repo}}/actions/workflows/{workflow}/runs"
            f"?branch={branch}&status=completed&per_page=1"
        ),
    )
    if problem is not None:
        return None, f"workflow runs: {problem}"
    raw_runs: object = response.get("workflow_runs") if response is not None else None
    if not isinstance(raw_runs, list) or not raw_runs:
        return None, None
    raw = cast("list[object]", raw_runs)[0]
    if not isinstance(raw, dict):
        return None, "workflow runs: malformed run"
    record = cast("dict[str, object]", raw)
    identifier = record.get("id")
    conclusion = _string(value=record, key="conclusion")
    head_sha = _string(value=record, key="head_sha")
    url = _string(value=record, key="html_url")
    if not isinstance(identifier, int) or not conclusion or not head_sha or not url:
        return None, "workflow runs: incomplete run"
    return Run(identifier=identifier, conclusion=conclusion, head_sha=head_sha, url=url), None


def failed_jobs(*, repo: Path, run: Run) -> tuple[tuple[FailedJob, ...], str | None]:
    """Read failed jobs and their logs from one failed workflow run."""
    response, problem = _cached_json(
        repo=repo,
        endpoint=f"repos/{{owner}}/{{repo}}/actions/runs/{run.identifier}/jobs?filter=latest&per_page=100",
    )
    if problem is not None:
        return (), f"run jobs: {problem}"
    raw_jobs: object = response.get("jobs") if response is not None else None
    if not isinstance(raw_jobs, list):
        return (), "run jobs: malformed response"
    jobs: list[FailedJob] = []
    for raw in cast("list[object]", raw_jobs):
        if not isinstance(raw, dict):
            continue
        record = cast("dict[str, object]", raw)
        if record.get("conclusion") != "failure":
            continue
        identifier = record.get("id")
        name = _string(value=record, key="name")
        if not isinstance(identifier, int) or name is None:
            return (), "run jobs: incomplete failed job"
        jobs.append(
            FailedJob(identifier=identifier, name=name, failed_step=_failed_step(raw=record))
        )
    return tuple(jobs), None


def failing_tests(*, repo: Path, job: FailedJob) -> tuple[tuple[str, ...] | None, str | None]:
    """Return unique test names found in the failed job's cached log."""
    text, problem = _cached_text(
        repo=repo, endpoint=f"repos/{{owner}}/{{repo}}/actions/jobs/{job.identifier}/logs"
    )
    if problem is not None:
        return None, problem
    matches = (match.group(1).strip() for match in _TEST_FAILURE_RE.finditer(text))
    tests = tuple(dict.fromkeys(matches))
    return tests, None


def _cached_json(*, repo: Path, endpoint: str) -> tuple[dict[str, object] | None, str | None]:
    text, problem = _cached_text(repo=repo, endpoint=endpoint)
    if problem is not None:
        return None, problem
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error.msg}"
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None, None


def _cached_text(*, repo: Path, endpoint: str) -> tuple[str, str | None]:
    completed = subprocess.run(  # noqa: S603 -- fixed gh API argv, endpoint is constructed here.
        ["gh", "api", "--cache", _CACHE_DURATION, endpoint],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=_GH_TIMEOUT_SECONDS,
    )
    if completed.returncode == 0:
        return completed.stdout, None
    detail = completed.stderr.strip() or completed.stdout.strip()
    return "", detail or f"gh exited {completed.returncode}"


def _failed_step(*, raw: dict[str, object]) -> str:
    steps = raw.get("steps")
    if isinstance(steps, list):
        for step in cast("list[object]", steps):
            if not isinstance(step, dict):
                continue
            record = cast("dict[str, object]", step)
            if record.get("conclusion") == "failure":
                name = _string(value=record, key="name")
                if name is not None:
                    return name
    return "unnamed failing step"


def _string(*, value: dict[str, object], key: str) -> str | None:
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) and candidate else None
