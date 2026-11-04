"""Find a concluded green ancestor while the newest master-CI run is pending."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_lookups import (
    UNKNOWN_RUN,
    CiRun,
    ancestor_of_branch,
    find_job,
    job_records,
    list_recent_runs,
    run_id_of,
    run_records,
    view_run_jobs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = ["green_ancestor"]

_PENDING_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})
_RED_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "action_required", "stale", "startup_failure"},
)


def green_ancestor(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    pending_run_id: str,
) -> tuple[str, str] | None:
    """Return the newest concluded green ancestor run, or no proof to pass on."""
    result = list_recent_runs(repo=repo, runner=runner, workflow=pipeline.workflow, branch=branch)
    if result.exit_code != 0:
        return None
    runs = _readable_runs(result=result)
    if runs is None:
        return None
    candidate = _newest_concluded_run(
        repo=repo,
        runner=runner,
        pipeline=pipeline,
        pending_run_id=pending_run_id,
        runs=runs,
    )
    if candidate is None:
        return None
    run_id, head_sha, conclusion = candidate
    if conclusion != "success":
        return None
    if ancestor_of_branch(repo=repo, runner=runner, commit=head_sha, branch=branch) is not True:
        return None
    return run_id, head_sha


def _readable_runs(*, result: CommandResult) -> list[object] | None:
    try:
        return run_records(result=result)
    except json.JSONDecodeError:
        return None


def _readable_jobs(*, result: CommandResult) -> list[object] | None:
    try:
        return job_records(result=result)
    except json.JSONDecodeError:
        return None


def _newest_concluded_run(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    pending_run_id: str,
    runs: list[object],
) -> tuple[str, str, str] | None:
    ordered = _ordered_recent_runs(runs=runs)
    if ordered is None:
        return None
    for run in ordered:
        candidate = _concluded_candidate(
            repo=repo,
            runner=runner,
            pipeline=pipeline,
            pending_run_id=pending_run_id,
            run=run,
        )
        if candidate is not None:
            return candidate
    return None


def _ordered_recent_runs(*, runs: list[object]) -> list[CiRun] | None:
    ordered: list[CiRun] = []
    for raw in runs:
        if not isinstance(raw, dict):
            return None
        run = cast("CiRun", raw)
        created_at = run.get("createdAt")
        if not isinstance(created_at, str) or not created_at:
            return None
        ordered.append(run)
    return sorted(ordered, key=lambda one: str(one.get("createdAt")), reverse=True)


def _concluded_candidate(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    pending_run_id: str,
    run: CiRun,
) -> tuple[str, str, str] | None:
    status = run.get("status")
    run_id = run_id_of(run=run)
    head_sha = run.get("headSha")
    if (
        (isinstance(status, str) and status in _PENDING_STATUSES)
        or run_id in (pending_run_id, UNKNOWN_RUN)
        or not isinstance(head_sha, str)
        or not head_sha
    ):
        return None
    result = view_run_jobs(repo=repo, runner=runner, run_id=run_id)
    if result.exit_code != 0:
        return None
    jobs = _readable_jobs(result=result)
    if jobs is None:
        return None
    job = find_job(jobs=jobs, name=pipeline.job)
    if job is None:
        return None
    conclusion = job.get("conclusion")
    if conclusion == "success" or conclusion in _RED_CONCLUSIONS:
        return run_id, head_sha, str(conclusion)
    return None
