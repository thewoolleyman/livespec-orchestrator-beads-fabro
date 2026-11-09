"""Classify the latest master-CI run into a verdict, a wait, or a refusal.

Split out of `_dispatcher_ci_preflight` along the cohesion seam between READING
the run listing, which stays there, and CLASSIFYING the one run it found, which
is all this module does. `classify_run` is the single entry point; the aggregate
job lookup, the green/red/pending conclusions and the no-verdict walk are its
private steps.

A RUN THAT CARRIES NO VERDICT IS NEITHER GREEN NOR RED. Its aggregate job is
missing (GitHub failed to create the job during an incident), or concluded
cancelled, skipped or startup_failure -- none of which judged the commit. ONE
classification covers all of them (`_walk_past_no_verdict`): the preflight walks
back to the newest run that does carry a verdict, exactly as it does for a run
that is still pending, and waits on the latest run when there is none.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_ancestors import (
    green_ancestor,
    newest_verdict_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_lookups import (
    UNKNOWN_RUN,
    CiJob,
    CiRun,
    ancestor_of_branch,
    find_job,
    job_records,
    run_id_of,
    view_run_jobs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    PENDING_REMEDY,
    PIPELINE_REMEDY,
    MasterCiOutcome,
    green_ancestor_outcome,
    no_verdict_ancestor_outcome,
    pass_outcome,
    red_outcome,
    unprovable_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_wait import (
    PendingReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "classify_run",
    "unprovable_reading",
]

_GREEN_CONCLUSIONS: frozenset[str] = frozenset({"success"})
_PENDING_STATUSES: frozenset[str] = frozenset(
    {"queued", "in_progress", "waiting", "pending", "requested"},
)
_RED_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "timed_out", "action_required", "stale"},
)
# A cancelled, skipped or startup-failed aggregate job never judged the commit,
# so it is the same reading as a run whose aggregate job does not exist at all.
_NO_VERDICT_CONCLUSIONS: frozenset[str] = frozenset({"cancelled", "skipped", "startup_failure"})


def classify_run(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    first: object,
) -> MasterCiOutcome | PendingReading:
    if not isinstance(first, dict):
        return unprovable_reading(
            pipeline=pipeline,
            branch=branch,
            cause="unexpected `gh run list` record shape",
            remedy=PIPELINE_REMEDY,
        )
    run = cast("CiRun", first)
    run_id = run_id_of(run=run)
    status = run.get("status")
    if isinstance(status, str) and status in _PENDING_STATUSES:
        return _ancestor_or_pending(
            repo=repo,
            runner=runner,
            pipeline=pipeline,
            branch=branch,
            pending=PendingReading(run_id=run_id, status=status),
        )
    return _classify_job(repo=repo, runner=runner, pipeline=pipeline, branch=branch, run_id=run_id)


def _classify_job(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    run_id: str,
) -> MasterCiOutcome | PendingReading:
    result = view_run_jobs(repo=repo, runner=runner, run_id=run_id)
    if result.exit_code != 0:
        return unprovable_reading(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause=f"the aggregate-job lookup failed: {result.stderr.strip() or '<empty stderr>'}",
            remedy=PIPELINE_REMEDY,
        )
    jobs = job_records(result=result)
    if jobs is None:
        return unprovable_reading(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause="unexpected `gh run view` payload shape",
            remedy=PIPELINE_REMEDY,
        )
    job = find_job(jobs=jobs, name=pipeline.job)
    if job is None:
        return _walk_past_no_verdict(
            repo=repo,
            runner=runner,
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            reason=f"aggregate job `{pipeline.job}` is missing from run {run_id}",
        )
    conclusion = job.get("conclusion")
    if conclusion in _NO_VERDICT_CONCLUSIONS:
        return _walk_past_no_verdict(
            repo=repo,
            runner=runner,
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            reason=f"aggregate job `{pipeline.job}` concluded `{conclusion}` on run {run_id}",
        )
    classification = _classify_conclusion(pipeline=pipeline, branch=branch, run_id=run_id, job=job)
    if isinstance(classification, MasterCiOutcome):
        return classification
    return _ancestor_or_pending(
        repo=repo,
        runner=runner,
        pipeline=pipeline,
        branch=branch,
        pending=classification,
    )


def _walk_past_no_verdict(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    run_id: str,
    reason: str,
) -> MasterCiOutcome | PendingReading:
    """Treat a run carrying no verdict as a pending one: walk back, else wait.

    The walk lands on the newest other run whose aggregate job is green or red.
    Red refuses on that run. Green passes only while its head is an ancestor of
    the branch head. With no such run the latest run is waited on, never refused.
    """
    waiting = PendingReading(run_id=run_id, status="without a verdict")
    verdict = newest_verdict_run(
        repo=repo, runner=runner, pipeline=pipeline, branch=branch, skipped_run_id=run_id
    )
    if verdict is None:
        return waiting
    verdict_run_id, head_sha, conclusion = verdict
    if conclusion != "success":
        return red_outcome(
            pipeline=pipeline, branch=branch, run_id=verdict_run_id, conclusion=conclusion
        )
    if ancestor_of_branch(repo=repo, runner=runner, commit=head_sha, branch=branch) is not True:
        return waiting
    return no_verdict_ancestor_outcome(
        pipeline=pipeline,
        branch=branch,
        run_id=verdict_run_id,
        head_sha=head_sha,
        no_verdict_run_id=run_id,
        no_verdict_reason=reason,
    )


def _ancestor_or_pending(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    pending: PendingReading,
) -> MasterCiOutcome | PendingReading:
    ancestor = green_ancestor(
        repo=repo,
        runner=runner,
        pipeline=pipeline,
        branch=branch,
        pending_run_id=pending.run_id,
    )
    if ancestor is None:
        return pending
    run_id, head_sha = ancestor
    return green_ancestor_outcome(
        pipeline=pipeline,
        branch=branch,
        run_id=run_id,
        head_sha=head_sha,
        pending_run_id=pending.run_id,
        pending_status=pending.status,
    )


def _classify_conclusion(
    *, pipeline: MasterCiPipeline, branch: str, run_id: str, job: CiJob
) -> MasterCiOutcome | PendingReading:
    job_status = job.get("status")
    conclusion = job.get("conclusion")
    if isinstance(job_status, str) and job_status in _PENDING_STATUSES:
        return PendingReading(run_id=run_id, status=job_status)
    if conclusion in _RED_CONCLUSIONS:
        return red_outcome(
            pipeline=pipeline, branch=branch, run_id=run_id, conclusion=str(conclusion)
        )
    if conclusion not in _GREEN_CONCLUSIONS:
        return unprovable_reading(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause=f"aggregate job conclusion `{conclusion}` is neither green nor red",
            remedy=PENDING_REMEDY,
        )
    return pass_outcome(pipeline=pipeline, branch=branch, run_id=run_id)


def unprovable_reading(
    *,
    pipeline: MasterCiPipeline,
    branch: str,
    cause: str,
    remedy: str,
    run_id: str = UNKNOWN_RUN,
) -> MasterCiOutcome:
    return unprovable_outcome(
        pipeline=pipeline, branch=branch, run_id=run_id, cause=cause, remedy=remedy
    )
