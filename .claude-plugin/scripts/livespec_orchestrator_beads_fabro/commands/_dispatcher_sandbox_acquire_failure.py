"""Classify the terminal that follows a failed sandbox acquisition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

SANDBOX_ACQUIRE_FAILURE = "sandbox-acquire-failure"
_PREFIX = "could not acquire the environment: sandbox acquire failed"

__all__: list[str] = [
    "SANDBOX_ACQUIRE_FAILURE",
    "sandbox_acquire_failure_outcome",
]


def sandbox_acquire_failure_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    failure: object,
) -> DispatchOutcome | None:
    """Map the measured post-checkpoint failure to the blocked lifecycle."""
    if inspect is None or inspect.status_kind != "failed":
        return None
    record = fabro_inspect_record(payload=inspect.payload)
    if record is None or not _workflow_error(record=record):
        return None
    cause = getattr(failure, "cause", None)
    if not isinstance(cause, str) or not cause.startswith(_PREFIX):
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_id or '(not parsed)'} ended {SANDBOX_ACQUIRE_FAILURE}: {cause}; "
            "item will be marked blocked/needs-human"
        ),
        needs_human_kind=SANDBOX_ACQUIRE_FAILURE,
        needs_human_reason=cause,
        final_git_commit_sha=_final_git_commit_sha(record=record),
        fabro_run_id=run_id,
        fabro_failure_cause=cause,
        fabro_failure_category=getattr(failure, "category", None),
        fabro_failure_signature=getattr(failure, "signature", None),
        provider_usage_limit=getattr(failure, "provider_usage_limit", False),
        provider_usage_limit_provider=getattr(failure, "provider_usage_limit_provider", None),
    )


def _workflow_error(*, record: Mapping[str, object]) -> bool:
    status = record.get("status")
    return (
        isinstance(status, Mapping)
        and cast("Mapping[str, object]", status).get("reason") == "workflow_error"
    )


def _final_git_commit_sha(*, record: Mapping[str, object]) -> str | None:
    conclusion = record.get("conclusion")
    if not isinstance(conclusion, Mapping):
        return None
    commit = cast("Mapping[str, object]", conclusion).get("final_git_commit_sha")
    return commit if isinstance(commit, str) and commit else None
