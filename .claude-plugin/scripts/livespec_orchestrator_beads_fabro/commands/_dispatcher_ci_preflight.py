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

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
    resolve_master_ci_pipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_classify import (
    classify_run,
    unprovable_reading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_lookup_failure import (
    lookup_failure_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_lookups import (
    UNKNOWN_RUN,
    list_runs,
    run_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    BRANCH_REMEDY,
    NO_RUNS_REMEDY,
    PIPELINE_REMEDY,
    MasterCiOutcome,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "master_ci_preflight",
]

_UNRESOLVED_BRANCH = "<unresolved>"
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
        return lookup_failure_outcome(
            repo=repo, runner=runner, pipeline=pipeline, branch=branch, result=result
        )
    runs = run_records(result=result)
    if runs is None:
        return unprovable_reading(
            pipeline=pipeline,
            branch=branch,
            cause="unexpected `gh run list` payload shape",
            remedy=PIPELINE_REMEDY,
        )
    if not runs:
        if observed_runs:
            return PendingReading(run_id=UNKNOWN_RUN, status=TRANSIENT_EMPTY_RUN_LISTING)
        return unprovable_reading(
            pipeline=pipeline,
            branch=branch,
            cause="the resolved pipeline has no runs yet on the resolved default branch",
            remedy=NO_RUNS_REMEDY,
        )
    return classify_run(repo=repo, runner=runner, pipeline=pipeline, branch=branch, first=runs[0])
