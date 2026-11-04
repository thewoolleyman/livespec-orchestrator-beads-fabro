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
    "attempt_failed_jobs_rerun",
    "classify_failed_job",
]

_TEARDOWN_STEP_MARKERS: tuple[str, ...] = ("post ", "cleanup", "stop container")
_TEARDOWN_LOG_MARKERS: tuple[str, ...] = (
    "custom container implementation failed",
    "container implementation failed",
    "runner failed to start",
)
_OOM_MARKERS: tuple[str, ...] = (
    "out of memory",
    "oom-kill",
    "oom killed",
    "exceeded its memory limit",
    "exceeded memory limit",
)
_TIMEOUT_MARKERS: tuple[str, ...] = (
    "exceeded the maximum execution time",
    "maximum execution time",
    "job exceeded the maximum execution time",
)
_RUN_ID = re.compile(r"/actions/runs/(?P<run_id>\d+)(?:/|$)")


@dataclass(frozen=True, kw_only=True)
class FailedJobClassification:
    """One conservative attribution and the evidence that established it."""

    kind: str
    evidence: tuple[str, ...]


def classify_failed_job(*, job: Mapping[str, object], log: str) -> FailedJobClassification:
    """Classify one failed job, preferring explicit kill/timeout evidence.

    A pytest assertion does not override an OOM kill or a job timeout: those
    are infrastructure observations even when they interrupt the test runner.
    With no matching infrastructure evidence the answer remains unattributed.
    """
    combined = "\n".join((_string(value=job.get("conclusion")), log))
    if evidence := _matched_log_evidence(text=combined, markers=_OOM_MARKERS, label="oom-kill"):
        return FailedJobClassification(kind="oom-kill", evidence=evidence)
    if evidence := _matched_log_evidence(
        text=combined,
        markers=_TIMEOUT_MARKERS,
        label="job-timeout",
    ):
        return FailedJobClassification(kind="job-timeout", evidence=evidence)
    failed_steps = _failed_teardown_steps(job=job)
    teardown_log = _matched_log_evidence(
        text=log,
        markers=_TEARDOWN_LOG_MARKERS,
        label="log",
    )
    if failed_steps and _all_non_teardown_steps_succeeded(job=job):
        evidence = (f"failed teardown steps: {', '.join(failed_steps)}", *teardown_log)
        return FailedJobClassification(kind="runner-teardown", evidence=evidence)
    if teardown_log and _all_non_teardown_steps_succeeded(job=job):
        return FailedJobClassification(kind="runner-teardown", evidence=teardown_log)
    return FailedJobClassification(kind="unattributed", evidence=())


def attempt_failed_jobs_rerun(
    *,
    failed_check_names: list[str],
    failures: tuple[TerminalCheckFailure, ...],
    plan: DispatchPlan,
    pr_number: int,
    runner: CommandRunner,
    journal: JournalWriter,
) -> str | None:
    """Request one conservative failed-jobs rerun, or decline without side effects.

    Every failed job in the workflow must carry an infrastructure attribution.
    An unreadable run, log, or changed-file list is deliberately a decline: the
    normal merge-poll terminal failure remains the safe outcome.
    """
    run_id = _workflow_run_id(failures=failures, failed_check_names=failed_check_names)
    if run_id is None:
        return None
    jobs_result = runner.run(
        argv=["gh", "run", "view", run_id, "--json", "jobs"],
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
    classified = _classify_jobs(run_id=run_id, jobs=jobs, plan=plan, runner=runner, journal=journal)
    if classified is None or any(item.kind == "unattributed" for item in classified):
        return None
    changed = runner.run(
        argv=["gh", "pr", "diff", str(pr_number), "--name-only"],
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
            "failed_jobs": [
                {"name": item.name, "class": item.kind, "evidence": item.evidence}
                for item in classified
            ],
            "outcome": "requested" if rerun.exit_code == 0 else "rejected",
        }
    )
    return run_id if rerun.exit_code == 0 else None


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


def _failed_jobs(*, stdout: str) -> tuple[Mapping[str, object], ...] | None:
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return None
    return tuple(
        cast("Mapping[str, object]", job)
        for job in cast("list[object]", payload["jobs"])
        if isinstance(job, Mapping) and _is_failed(step=job)
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


def _matched_log_evidence(*, text: str, markers: tuple[str, ...], label: str) -> tuple[str, ...]:
    matched = tuple(marker for marker in markers if marker in text.lower())
    if not matched:
        return ()
    if label == "log":
        return (f"log: {text.strip()}",)
    return tuple(f"{label}: {marker}" for marker in matched)


def _failed_teardown_steps(*, job: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        name
        for step in _steps(job=job)
        for name in [_string(value=step.get("name"))]
        if _is_failed(step=step) and _is_teardown_step(name=name)
    )


def _all_non_teardown_steps_succeeded(*, job: Mapping[str, object]) -> bool:
    return all(
        _is_teardown_step(name=_string(value=step.get("name"))) or _is_succeeded(step=step)
        for step in _steps(job=job)
    )


def _steps(*, job: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = job.get("steps")
    if not isinstance(raw, list):
        return ()
    values = cast("list[object]", raw)
    return tuple(
        cast("Mapping[str, object]", value) for value in values if isinstance(value, Mapping)
    )


def _is_teardown_step(*, name: str) -> bool:
    return any(marker in name.lower() for marker in _TEARDOWN_STEP_MARKERS)


def _is_failed(*, step: Mapping[str, object]) -> bool:
    return _string(value=step.get("conclusion")).lower() in {"failure", "cancelled", "timed_out"}


def _is_succeeded(*, step: Mapping[str, object]) -> bool:
    return _string(value=step.get("conclusion")).lower() in {"success", "skipped"}


def _string(*, value: object) -> str:
    return value if isinstance(value, str) else ""
