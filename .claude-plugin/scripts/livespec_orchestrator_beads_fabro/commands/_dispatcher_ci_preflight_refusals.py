"""How a master-CI preflight outcome READS: its operator text and its journal record.

Split out of `_dispatcher_ci_preflight` along the cohesion seam between
DECIDING an outcome -- the lookups and the classification, which stay there --
and SAYING it, which is all this module does.

THE REMEDY PROSE IS THE LOAD-BEARING HALF OF THE FAIL-OPEN RETIREMENT. Making
an unverifiable host refuse instead of proceed is only safe if the refusal tells
the operator how to get moving again; a refusal that merely says "unprovable"
parks an adopter with no route out and earns itself an env-var bypass within the
week. So every unprovable refusal built here names BOTH the direct remedy and
the committed `dispatcher.step_waivers` escape -- the sanctioned way a
repository that genuinely cannot verify proceeds, visibly and with an owner,
rather than silently.

Both sanctioned non-waived outcomes of a pre-dispatch step are journaled: a
PASS is a record, not an absence (`SPECIFICATION/contracts.md`, the
dispatch-preflight step discipline).
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MASTER_CI_KEY,
    MasterCiPipeline,
    pipeline_resolution_sentence,
)

__all__: list[str] = [
    "BRANCH_REMEDY",
    "CREDENTIAL_REMEDY",
    "NO_RUNS_REMEDY",
    "PENDING_REMEDY",
    "PIPELINE_REMEDY",
    "STAGE",
    "STEP",
    "MasterCiOutcome",
    "MasterCiRefusal",
    "pass_outcome",
    "pending_outcome",
    "red_outcome",
    "unprovable_outcome",
]

STAGE = "master-ci-preflight"
STEP = "master-ci"

_REASON_GREEN = "master-ci-green"
_REASON_RED = "master-ci-red"
_REASON_UNPROVABLE = "master-ci-unprovable"
_REASON_PENDING = "master-ci-pending"
_STATUS_DEFERRED = "deferred"

_WAIVER_ESCAPE = (
    "or commit a `master-ci` entry under `dispatcher.step_waivers` (step, owner, "
    "reason) -- the sanctioned step-waiver escape for a repository that genuinely "
    "cannot verify"
)

CREDENTIAL_REMEDY = (
    "install and authenticate `gh` on the dispatching host (`gh auth login`), " f"{_WAIVER_ESCAPE}."
)
PIPELINE_REMEDY = (
    "declare this repository's aggregate workflow and job under the committed "
    f"`{MASTER_CI_KEY}` key so the lookup resolves them, {_WAIVER_ESCAPE}."
)
NO_RUNS_REMEDY = (
    "run the pipeline on the resolved default branch at least once so there is a "
    f"run to read, {_WAIVER_ESCAPE}."
)
BRANCH_REMEDY = (
    "make the target's default branch resolvable (`git remote set-head origin "
    f"--auto`, or a reachable `gh repo view`), {_WAIVER_ESCAPE}."
)
PENDING_REMEDY = "retry the dispatch when the run concludes."

_RECOVERY = [
    " ".join(
        (
            "For a master-health-restoration item parked behind a red default branch,",
            "drive it in-session through worktree -> PR -> merge; PR CI is independent",
            "of the default branch.",
        )
    ),
    " ".join(
        (
            "See AGENTS.md and .claude-plugin/prose/implement.md Step 0 for the",
            "documented escape hatch and the repeat-flake caveat.",
        )
    ),
]

_RECOVERY_TEXT = (
    "Recovery: if this is a master-health-restoration item parked behind a red "
    "default branch, drive it in-session through worktree -> PR -> merge; PR CI is "
    "independent of the default branch. See AGENTS.md and "
    ".claude-plugin/prose/implement.md Step 0. For repeat-flakes, rerun attempts are "
    "diagnostic only and may not produce a green default branch.\n"
)


@dataclass(frozen=True, kw_only=True)
class MasterCiRefusal:
    """Terminal master-CI preflight refusal, ready to emit and journal."""

    detail: str
    record: dict[str, object]


@dataclass(frozen=True, kw_only=True)
class MasterCiOutcome:
    """A preflight verdict: always a journal record, plus a refusal when it refused.

    The record is carried on BOTH arms because a pre-dispatch step's pass is a
    sanctioned journaled outcome in its own right; a caller that journals only
    when `refusal` is set would leave the passing dispatch with no evidence the
    step ran at all.
    """

    refusal: MasterCiRefusal | None
    record: dict[str, object]


def pass_outcome(*, pipeline: MasterCiPipeline, branch: str, run_id: str) -> MasterCiOutcome:
    """The proven-green outcome: dispatch proceeds, and the pass is journaled."""
    return MasterCiOutcome(
        refusal=None,
        record={
            **_identity(pipeline=pipeline, branch=branch, run_id=run_id),
            "terminal": False,
            "status": "passed",
            "reason": _REASON_GREEN,
        },
    )


def red_outcome(
    *, pipeline: MasterCiPipeline, branch: str, run_id: str, conclusion: str
) -> MasterCiOutcome:
    """The proven-red outcome: refuse, naming the red run and its conclusion."""
    return _refusing(
        pipeline=pipeline,
        branch=branch,
        run_id=run_id,
        reason=_REASON_RED,
        cause=f"aggregate job `{pipeline.job}` concluded {conclusion} on run {run_id}",
        remedy=PENDING_REMEDY,
    )


def pending_outcome(
    *, pipeline: MasterCiPipeline, branch: str, run_id: str, status: str, waited: float
) -> MasterCiOutcome:
    """The bounded wait expiring on a run that has not concluded: defer, never fail.

    This is the ONE deferral form of a pre-dispatch refusal. It stops the
    dispatch exactly as a refusal does -- which is why it carries a
    `MasterCiRefusal`, the thing the step gate reads to return exit 3 before the
    work item is claimed -- while its journal record reads as a verdict that has
    not arrived rather than one that came back bad.

    THREE THINGS IT DELIBERATELY DOES NOT BORROW from `_refusing`, each the
    repair of a measured misreport. The `ERROR:` prefix and the words "not
    proven green" announce a run that came back bad, which a still-running one
    has not. And the red-default-branch recovery text sends the operator to
    restore master health through worktree -> PR -> merge, which applies only to
    a RED default branch and is work nobody owes here -- so the `recovery` key is
    ABSENT from this record rather than present and empty, because an empty
    recovery list reads as "no route out was found" instead of "none applies".
    """
    waited_seconds = int(waited)
    record: dict[str, object] = {
        **_identity(pipeline=pipeline, branch=branch, run_id=run_id),
        "terminal": True,
        "status": _STATUS_DEFERRED,
        "reason": _REASON_PENDING,
        "detail": f"the latest `{branch}` run {run_id} is still {status} after {waited_seconds}s",
        "remedy": PENDING_REMEDY,
        "run_status": status,
        "waited_seconds": waited_seconds,
    }
    detail = _pending_detail(
        pipeline=pipeline,
        branch=branch,
        run_id=run_id,
        status=status,
        waited_seconds=waited_seconds,
    )
    return MasterCiOutcome(refusal=MasterCiRefusal(detail=detail, record=record), record=record)


def unprovable_outcome(
    *, pipeline: MasterCiPipeline, branch: str, run_id: str, cause: str, remedy: str
) -> MasterCiOutcome:
    """The absence-of-proof outcome: refuse, naming the cause and the way out."""
    return _refusing(
        pipeline=pipeline,
        branch=branch,
        run_id=run_id,
        reason=_REASON_UNPROVABLE,
        cause=cause,
        remedy=remedy,
    )


def _refusing(
    *,
    pipeline: MasterCiPipeline,
    branch: str,
    run_id: str,
    reason: str,
    cause: str,
    remedy: str,
) -> MasterCiOutcome:
    record: dict[str, object] = {
        **_identity(pipeline=pipeline, branch=branch, run_id=run_id),
        "terminal": True,
        "status": "failed",
        "reason": reason,
        "detail": cause,
        "remedy": remedy,
        "recovery": _RECOVERY,
    }
    detail = _detail(pipeline=pipeline, branch=branch, run_id=run_id, cause=cause, remedy=remedy)
    # The SAME record object on both arms: the caller journals `outcome.record`
    # unconditionally, so a refusal whose two records could drift would journal
    # one thing and print another.
    return MasterCiOutcome(refusal=MasterCiRefusal(detail=detail, record=record), record=record)


def _identity(*, pipeline: MasterCiPipeline, branch: str, run_id: str) -> dict[str, object]:
    """The keys every master-CI journal record carries, pass or refusal alike."""
    return {
        "stage": STAGE,
        "step": STEP,
        "branch": branch,
        "workflow": pipeline.workflow,
        "aggregate_job": pipeline.job,
        "pipeline_resolution": pipeline.resolution,
        "declaring_key": MASTER_CI_KEY,
        "run_database_id": run_id,
    }


def _pending_detail(
    *, pipeline: MasterCiPipeline, branch: str, run_id: str, status: str, waited_seconds: int
) -> str:
    """The deferral's operator text, which leads with the fact it has not failed.

    The ratified clause puts five things on the FIRST line -- the run, its
    pending status, the branch, how long the preflight waited, and that it has
    not failed -- because that line is what a scrolling operator reads, and a
    first line that only said "deferred" would leave the failure reading intact.
    """
    return (
        f"The latest `{branch}` run {run_id} of workflow `{pipeline.workflow}` is still "
        f"{status} and has not failed; the master-CI preflight waited {waited_seconds}s "
        "for its verdict and is deferring this dispatch.\n"
        f"Resolved default branch: {branch}\n"
        f"{pipeline_resolution_sentence(pipeline=pipeline)}\n"
        f"Run databaseId: {run_id}\n"
        f"Aggregate job: {pipeline.job}\n"
        f"Remedy: {PENDING_REMEDY}\n"
    )


def _detail(
    *, pipeline: MasterCiPipeline, branch: str, run_id: str, cause: str, remedy: str
) -> str:
    return (
        f"ERROR: the latest `{branch}` run of workflow `{pipeline.workflow}` is not "
        f"proven green at aggregate job `{pipeline.job}`; refusing dispatch before "
        "sandbox work.\n"
        f"Resolved default branch: {branch}\n"
        f"{pipeline_resolution_sentence(pipeline=pipeline)}\n"
        f"Run databaseId: {run_id}\n"
        f"Reason: {cause}\n"
        f"Remedy: {remedy}\n"
        f"{_RECOVERY_TEXT}"
    )
