"""Conservative evidence classification for a failed workflow job.

The merge engine owns polling and terminal outcomes.  This leaf owns only the
fixed, committed evidence patterns that decide whether a failed job is a
runner fault rather than a product failure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_classify import (
    FailedJobClassification,
    classify_failed_job,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_filing import (
    file_flake_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import GH_TIMEOUT_SECONDS
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_status import (
    TerminalCheckFailure,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "FailedJobClassification",
    "FailedJobsRerun",
    "FailedRequiredChecks",
    "attempt_failed_jobs_rerun",
    "classify_failed_job",
]

_RUN_ID = re.compile(r"/actions/runs/(?P<run_id>\d+)(?:/|$)")


@dataclass(frozen=True, kw_only=True)
class FailedJobsRerun:
    """One request attempt, including a forge rejection that consumes the bound."""

    workflow_run: str
    requested: bool
    prior_attempt: int


@dataclass(frozen=True, kw_only=True)
class FailedRequiredChecks:
    """The required checks that failed terminally on one pull request head."""

    names: list[str]
    failures: tuple[TerminalCheckFailure, ...]
    pr_number: int
    pr_head: str | None


def attempt_failed_jobs_rerun(
    *,
    failed: FailedRequiredChecks,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> FailedJobsRerun | None:
    """Request one conservative failed-jobs rerun, or decline without side effects.

    Every failed job in the workflow must carry an infrastructure attribution.
    An unreadable run, log, or changed-file list is deliberately a decline: the
    normal merge-poll terminal failure remains the safe outcome.
    """
    run_id = _workflow_run_id(failures=failed.failures, failed_check_names=failed.names)
    if run_id is None:
        return None
    jobs_result = runner.run(
        argv=["gh", "run", "view", run_id, "--json", "attempt,jobs"],
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="merge-poll-failed-jobs-view",
        result=jobs_result,
    )
    jobs = _failed_jobs(stdout=jobs_result.stdout) if jobs_result.exit_code == 0 else None
    if not jobs:
        return None
    prior_attempt = _run_attempt(stdout=jobs_result.stdout)
    classified = _classify_jobs(run_id=run_id, jobs=jobs, plan=plan, runner=runner, journal=journal)
    if classified is None or any(item.kind == "unattributed" for item in classified):
        return None
    changed = runner.run(
        argv=["gh", "pr", "diff", str(failed.pr_number), "--name-only"],
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="merge-poll-changed-files", result=changed)
    if changed.exit_code != 0 or _names_touched_test(logs=classified, changed_files=changed.stdout):
        return None
    rerun = runner.run(
        argv=["gh", "run", "rerun", run_id, "--failed"],
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": "merge-poll-failed-jobs-rerun",
            "workflow_run": run_id,
            "pr_number": failed.pr_number,
            "pr_head": failed.pr_head,
            "prior_attempt": prior_attempt,
            "failed_jobs": [
                {"name": item.name, "class": item.kind, "evidence": item.evidence}
                for item in classified
            ],
            "outcome": "requested" if rerun.exit_code == 0 else "rejected",
            "failure_reason": rerun.stderr if rerun.exit_code != 0 else None,
        }
    )
    if rerun.exit_code != 0:
        return FailedJobsRerun(workflow_run=run_id, requested=False, prior_attempt=prior_attempt)
    filing = file_flake_item(
        run_id=run_id,
        jobs=tuple((item.name, item.kind, item.evidence) for item in classified),
        plan=plan,
        runner=runner,
    )
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": "merge-poll-failed-jobs-rerun-flake",
            "workflow_run": run_id,
            "outcome": "filed" if filing is None else "failed",
            "failure_reason": filing,
        }
    )
    return FailedJobsRerun(workflow_run=run_id, requested=True, prior_attempt=prior_attempt)


@dataclass(frozen=True, kw_only=True)
class _ClassifiedJob:
    name: str
    kind: str
    evidence: tuple[str, ...]
    log: str


def _workflow_run_id(
    *, failures: tuple[TerminalCheckFailure, ...], failed_check_names: list[str]
) -> str | None:
    matched = {
        match.group("run_id")
        for failure in failures
        if failure.name in failed_check_names and failure.details_url is not None
        for match in [_RUN_ID.search(failure.details_url)]
        if match is not None
    }
    return next(iter(matched)) if len(matched) == 1 else None


def _run_attempt(*, stdout: str) -> int:
    attempt = cast("dict[str, object]", json.loads(stdout)).get("attempt")
    return attempt if isinstance(attempt, int) else 1


def _failed_jobs(*, stdout: str) -> tuple[Mapping[str, object], ...] | None:
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    document = cast("dict[str, object]", payload)
    jobs = document.get("jobs")
    if not isinstance(jobs, list):
        return None
    return tuple(
        cast("Mapping[str, object]", job)
        for job in cast("list[object]", jobs)
        if isinstance(job, Mapping) and _is_failed_job(job=cast("Mapping[str, object]", job))
    )


def _classify_jobs(
    *,
    run_id: str,
    jobs: tuple[Mapping[str, object], ...],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> tuple[_ClassifiedJob, ...] | None:
    classified: list[_ClassifiedJob] = []
    for job in jobs:
        job_id = _string(value=job.get("databaseId")) or str(job.get("databaseId", ""))
        name = _string(value=job.get("name"))
        if not job_id or not name:
            return None
        result = runner.run(
            argv=["gh", "run", "view", run_id, "--job", job_id, "--log"],
            cwd=plan.repo,
            timeout_seconds=GH_TIMEOUT_SECONDS,
        )
        journal_stage(journal=journal, plan=plan, stage="merge-poll-failed-job-log", result=result)
        if result.exit_code != 0:
            return None
        attribution = classify_failed_job(job=job, log=result.stdout)
        classified.append(
            _ClassifiedJob(
                name=name,
                kind=attribution.kind,
                evidence=attribution.evidence,
                log=result.stdout,
            )
        )
    return tuple(classified)


def _names_touched_test(*, logs: tuple[_ClassifiedJob, ...], changed_files: str) -> bool:
    changed = set(changed_files.splitlines())
    return any(
        path in changed
        for item in logs
        for path in re.findall(r"([\w./-]+\.py)::[\w\[\]-]+", item.log)
    )


def _is_failed_job(*, job: Mapping[str, object]) -> bool:
    conclusion = _string(value=job.get("conclusion")).lower()
    return conclusion in {"failure", "cancelled", "timed_out"}


def _string(*, value: object) -> str:
    return value if isinstance(value, str) else ""
