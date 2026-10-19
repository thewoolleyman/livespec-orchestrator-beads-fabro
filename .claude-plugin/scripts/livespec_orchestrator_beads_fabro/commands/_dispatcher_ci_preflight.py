"""Host-side master-CI preflight for Fabro dispatch admission safety.

ABSENCE OF PROOF REFUSES. The three fail-open cases this preflight used to
document -- no `gh` binary, no stored `gh` credential, no runs yet -- are
RETIRED: each is now an unprovable refusal naming its remedy and the committed
step-waiver escape. A host that cannot check is a host that cannot prove the
default branch green, and proceeding on that was the whole defect
(`SPECIFICATION/contracts.md`, the master-CI pipeline resolution clause).

A STILL-PENDING LATEST RUN IS THE ONE READING THAT IS NEITHER. It used to take
the unprovable arm, which reported a run that had not failed as a failure; it is
now a `PendingReading` the preflight WAITS on, and only the bounded wait expiring
turns one into an outcome -- the deferral, never a refusal. The rationale and the
seam are in `_dispatcher_ci_preflight_wait`.

THE BRANCH IS NEVER HARD-CODED. It is resolved per the ratified
default-branch-resolution rule, because under the retired branch literal an
adopter whose primary branch is `main` had a branch they do not have looked up
on their behalf -- and got a clean, plausible, empty answer for it.

A PRESENT-BUT-UNUSABLE DECLARATION REFUSES TOO, and refuses first, before any
git or forge read. It is the fail-open wearing a declaration's clothes: a typo
in a declared workflow name that slid onto the convention would admit the
dispatch on an unrelated pipeline's green, which is indistinguishable at the
call site from the repository's own pipeline passing.

WHAT is looked up comes from `_dispatcher_ci_pipeline_view`; the branch comes
from the shared `_dispatcher_default_branch` resolution every dispatch-path
stage uses; the forge reads come from `_dispatcher_ci_preflight_lookups`; HOW an
outcome reads comes from
`_dispatcher_ci_preflight_refusals`. This module is the classifier between them.
WHERE an outcome is journaled is none of the four: the pre-dispatch step gate
owns one journal handle and appends every step's record through it.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
    resolve_master_ci_pipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_lookups import (
    UNKNOWN_RUN,
    CiJob,
    CiRun,
    find_job,
    has_stored_credential,
    job_records,
    list_runs,
    run_id_of,
    run_records,
    view_run_jobs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    BRANCH_REMEDY,
    CREDENTIAL_REMEDY,
    NO_RUNS_REMEDY,
    PENDING_REMEDY,
    PIPELINE_REMEDY,
    MasterCiOutcome,
    pass_outcome,
    red_outcome,
    unprovable_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_wait import (
    TRANSIENT_EMPTY_RUN_LISTING,
    MasterCiWait,
    PendingReading,
    await_master_ci_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = [
    "master_ci_preflight",
]

_UNRESOLVED_BRANCH = "<unresolved>"
_STDERR_EXCERPT = 200
_GREEN_CONCLUSIONS: frozenset[str] = frozenset({"success"})
_PENDING_STATUSES: frozenset[str] = frozenset(
    {"queued", "in_progress", "waiting", "pending", "requested"},
)
_RED_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure"},
)
# Resolved once, at import, so the production effects are the signature's own
# default and no caller has to know the seam exists.
_DEFAULT_WAIT = MasterCiWait()


def master_ci_preflight(
    *, repo: Path, runner: CommandRunner, wait: MasterCiWait = _DEFAULT_WAIT
) -> MasterCiOutcome:
    """Prove the resolved default branch green at the resolved aggregate job.

    Returns the step's journaled outcome either way: a pass when the latest run
    of the resolved workflow on the resolved branch concluded green at the
    resolved aggregate job, a refusal for a red or unprovable reading, and the
    DEFERRAL when the latest run has still not concluded. A pending reading is
    never a refusal on its own: a run that has not concluded has not failed.
    """
    pipeline = resolve_master_ci_pipeline(cwd=repo)
    if pipeline.defect is not None:
        # Refused BEFORE the branch and forge reads: there is nothing to look
        # up. Resolving a branch first would only decorate the refusal, and
        # completing the declaration from the convention would prove a pipeline
        # the repository has already said is not its own.
        return unprovable_outcome(
            pipeline=pipeline,
            branch=_UNRESOLVED_BRANCH,
            run_id=UNKNOWN_RUN,
            cause=f"the declared master-CI pipeline is unusable: {pipeline.defect}",
            remedy=PIPELINE_REMEDY,
        )
    branch = resolve_default_branch(repo=repo, runner=runner)
    if branch is None:
        return unprovable_outcome(
            pipeline=pipeline,
            branch=_UNRESOLVED_BRANCH,
            run_id=UNKNOWN_RUN,
            cause="the target's default branch could not be resolved",
            remedy=BRANCH_REMEDY,
        )
    return await_master_ci_verdict(
        repo=repo,
        runner=runner,
        pipeline=pipeline,
        branch=branch,
        wait=wait,
        read_latest=_read_latest,
    )


def _read_latest(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    observed_runs: bool,
) -> MasterCiOutcome | PendingReading:
    result = list_runs(repo=repo, runner=runner, workflow=pipeline.workflow, branch=branch)
    if result.exit_code != 0:
        return _lookup_failure(
            repo=repo, runner=runner, pipeline=pipeline, branch=branch, result=result
        )
    runs = run_records(result=result)
    if runs is None:
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            cause="unexpected `gh run list` payload shape",
            remedy=PIPELINE_REMEDY,
        )
    if not runs:
        if observed_runs:
            return PendingReading(run_id=UNKNOWN_RUN, status=TRANSIENT_EMPTY_RUN_LISTING)
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            cause="the resolved pipeline has no runs yet on the resolved default branch",
            remedy=NO_RUNS_REMEDY,
        )
    return _classify_run(repo=repo, runner=runner, pipeline=pipeline, branch=branch, first=runs[0])


def _lookup_failure(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    result: CommandResult,
) -> MasterCiOutcome:
    """A failed run lookup: no usable credential, or a pipeline that will not resolve.

    An absent `gh` binary and an unauthenticated one land on the same arm on
    purpose: both make `gh auth token` fail, and both leave the operator with
    the same remedy.
    """
    excerpt = result.stderr.strip()[:_STDERR_EXCERPT] or "<empty stderr>"
    if not has_stored_credential(repo=repo, runner=runner):
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            cause=f"no usable `gh` credential on this host; `gh` exited {result.exit_code}",
            remedy=CREDENTIAL_REMEDY,
        )
    return _unprovable(
        pipeline=pipeline,
        branch=branch,
        cause=(
            f"the resolved pipeline could not be found; credentialed `gh` exited "
            f"{result.exit_code}: {excerpt}"
        ),
        remedy=PIPELINE_REMEDY,
    )


def _classify_run(
    *,
    repo: Path,
    runner: CommandRunner,
    pipeline: MasterCiPipeline,
    branch: str,
    first: object,
) -> MasterCiOutcome | PendingReading:
    if not isinstance(first, dict):
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            cause="unexpected `gh run list` record shape",
            remedy=PIPELINE_REMEDY,
        )
    run = cast("CiRun", first)
    run_id = run_id_of(run=run)
    status = run.get("status")
    if isinstance(status, str) and status in _PENDING_STATUSES:
        return PendingReading(run_id=run_id, status=status)
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
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause=f"the aggregate-job lookup failed: {result.stderr.strip() or '<empty stderr>'}",
            remedy=PIPELINE_REMEDY,
        )
    jobs = job_records(result=result)
    if jobs is None:
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause="unexpected `gh run view` payload shape",
            remedy=PIPELINE_REMEDY,
        )
    job = find_job(jobs=jobs, name=pipeline.job)
    if job is None:
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause=f"aggregate job `{pipeline.job}` is missing from run {run_id}",
            remedy=PIPELINE_REMEDY,
        )
    return _classify_conclusion(pipeline=pipeline, branch=branch, run_id=run_id, job=job)


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
        return _unprovable(
            pipeline=pipeline,
            branch=branch,
            run_id=run_id,
            cause=f"aggregate job conclusion `{conclusion}` is neither green nor red",
            remedy=PENDING_REMEDY,
        )
    return pass_outcome(pipeline=pipeline, branch=branch, run_id=run_id)


def _unprovable(
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
