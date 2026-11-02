"""The git/forge reads the master-CI preflight makes, and the shapes they return.

Split out of `_dispatcher_ci_preflight` along the seam between ASKING —
which argv, which timeout, which payload key — and CLASSIFYING what came back,
which stays there. The two change for different reasons: a `gh` output-shape
change touches only this module, and a policy change about what counts as proof
touches only the classifier.

THE DEFAULT-BRANCH RESOLUTION IS NO LONGER HERE. It began in this module, as the
preflight's own replacement for a hard-coded branch literal, and it now lives in
`_dispatcher_default_branch` because a SECOND dispatch-path stage -- the factory
workflow-file guard -- asks the same question, and the ratified clause has the
dispatch path reuse one resolution rather than each caller carrying its own. The
preflight imports it from there; nothing about what it does changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)

if TYPE_CHECKING:
    # Deferred deliberately: the post-merge janitor's VENUE resolution reuses
    # `resolve_default_branch`, and `_dispatcher_engine` imports that janitor
    # slice at module scope. A runtime import of the engine here would close
    # that ring and break the import, while these two names are only ever
    # annotations.
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
    )

__all__: list[str] = [
    "UNKNOWN_RUN",
    "CiJob",
    "CiRun",
    "ancestor_of_branch",
    "find_job",
    "has_stored_credential",
    "job_records",
    "list_recent_runs",
    "list_runs",
    "resolve_default_branch",
    "run_id_of",
    "run_records",
    "view_run_jobs",
]

_PREFLIGHT_TIMEOUT_SECONDS = 30.0

# The id a refusal names when no run was read at all — the same mark the journal
# record carries, so "which run?" has one answer across text and record.
UNKNOWN_RUN = "<none>"


class CiRun(TypedDict, total=False):
    """One `gh run list` record, as loosely as the forge actually returns it."""

    status: str | None
    conclusion: str | None
    databaseId: int | str | None
    headSha: str | None
    createdAt: str | None


class CiJob(TypedDict, total=False):
    """One job of a `gh run view --json jobs` payload."""

    name: str | None
    conclusion: str | None
    status: str | None


def has_stored_credential(*, repo: Path, runner: CommandRunner) -> bool:
    """Whether this host holds a `gh` credential it could have checked with."""
    return _gh(repo=repo, runner=runner, argv=["auth", "token"]).exit_code == 0


def list_runs(*, repo: Path, runner: CommandRunner, workflow: str, branch: str) -> CommandResult:
    """The latest run of `workflow` on `branch`, as `gh` reports it."""
    return _gh(
        repo=repo,
        runner=runner,
        argv=[
            "run",
            "list",
            "--branch",
            branch,
            "--limit",
            "1",
            "--workflow",
            workflow,
            "--json",
            "status,conclusion,databaseId",
        ],
    )


def list_recent_runs(
    *, repo: Path, runner: CommandRunner, workflow: str, branch: str
) -> CommandResult:
    """The recent runs needed to find a concluded ancestor while the latest is pending."""
    return _gh(
        repo=repo,
        runner=runner,
        argv=[
            "run",
            "list",
            "--branch",
            branch,
            "--limit",
            "100",
            "--workflow",
            workflow,
            "--json",
            "databaseId,headSha,status,conclusion,createdAt",
        ],
    )


def ancestor_of_branch(
    *, repo: Path, runner: CommandRunner, commit: str, branch: str
) -> bool | None:
    """Whether the forge says ``commit`` is the current branch head or its ancestor."""
    result = _gh(
        repo=repo,
        runner=runner,
        argv=[
            "api",
            f"repos/{{owner}}/{{repo}}/compare/{commit}...{branch}",
            "--jq",
            ".status",
        ],
    )
    if result.exit_code != 0:
        return None
    status = result.stdout.strip()
    if status in {"ahead", "identical"}:
        return True
    if status in {"behind", "diverged"}:
        return False
    return None


def view_run_jobs(*, repo: Path, runner: CommandRunner, run_id: str) -> CommandResult:
    """The jobs of one run, as `gh` reports them."""
    return _gh(repo=repo, runner=runner, argv=["run", "view", run_id, "--json", "jobs"])


def run_records(*, result: CommandResult) -> list[object] | None:
    """The `gh run list` records, or None when the payload is not the listed shape."""
    parsed: object = json.loads(result.stdout)
    if not isinstance(parsed, list):
        return None
    return cast("list[object]", parsed)


def job_records(*, result: CommandResult) -> list[object] | None:
    """The `gh run view` job records, or None when the payload is not that shape."""
    parsed: object = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        return None
    jobs_raw = cast("dict[str, object]", parsed).get("jobs")
    if not isinstance(jobs_raw, list):
        return None
    return cast("list[object]", jobs_raw)


def find_job(*, jobs: list[object], name: str) -> CiJob | None:
    """The named job among `jobs`, ignoring records that are not objects."""
    found: CiJob | None = None
    for raw_job in jobs:
        if isinstance(raw_job, dict):
            job_payload = cast("dict[str, object]", raw_job)
            if job_payload.get("name") == name:
                found = cast("CiJob", raw_job)
    return found


def run_id_of(*, run: CiRun) -> str:
    """The run's database id as a string, or the unknown-run mark."""
    raw = run.get("databaseId")
    return str(raw) if raw is not None else UNKNOWN_RUN


def _gh(*, repo: Path, runner: CommandRunner, argv: list[str]) -> CommandResult:
    return runner.run(
        argv=["gh", *argv],
        cwd=repo,
        timeout_seconds=_PREFLIGHT_TIMEOUT_SECONDS,
    )
