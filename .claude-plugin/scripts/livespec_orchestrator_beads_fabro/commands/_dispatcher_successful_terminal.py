"""Structured checkpoint evidence for a successful route behind run-store loss."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = [
    "SuccessfulTerminalEvidence",
    "successful_store_loss_evidence",
]

_RUN_STORE_LOSS_MESSAGE = "Worker exited before emitting a terminal run event: exit status: 0"


@dataclass(frozen=True, kw_only=True)
class SuccessfulTerminalEvidence:
    """The current run's checkpoint and its contradictory engine conclusion."""

    run_id: str
    timestamp: str
    current_node: str
    next_node_id: str
    commit_sha: str
    engine_status: str
    failure_cause: str
    failure_category: str | None


def successful_store_loss_evidence(
    *, run_id: str | None, inspect: FabroInspectResult | None
) -> SuccessfulTerminalEvidence | None:
    """Return the incident's structured evidence, or no override."""
    record = None if inspect is None else fabro_inspect_record(payload=inspect.payload)
    checkpoints = () if record is None else fabro_inspect_checkpoints(record=record)
    checkpoint: dict[str, Any] = {} if not checkpoints else checkpoints[-1]
    outcomes_raw: object = checkpoint.get("node_outcomes")
    outcomes = cast("dict[object, object]", outcomes_raw) if isinstance(outcomes_raw, dict) else {}
    final_raw: object = outcomes.get("verify_pr")
    final = cast("dict[object, object]", final_raw) if isinstance(final_raw, dict) else {}
    failure = None if inspect is None else inspect.failure
    timestamp_raw: object = checkpoint.get("timestamp")
    commit_raw: object = checkpoint.get("git_commit_sha")
    qualifies = bool(
        run_id is not None
        and inspect is not None
        and inspect.command.exit_code == 0
        and inspect.status_kind == "failed"
        and failure is not None
        and failure.cause == _RUN_STORE_LOSS_MESSAGE
        and record is not None
        and record.get("run_id") == run_id
        and checkpoint.get("current_node") == "verify_pr"
        and checkpoint.get("next_node_id") == "exit"
        and final.get("status") == "succeeded"
        and isinstance(timestamp_raw, str)
        and isinstance(commit_raw, str)
    )
    if not qualifies or failure is None:
        return None
    return SuccessfulTerminalEvidence(
        run_id=cast("str", run_id),
        timestamp=cast("str", timestamp_raw),
        current_node="verify_pr",
        next_node_id="exit",
        commit_sha=cast("str", commit_raw),
        engine_status="failed",
        failure_cause=cast("str", failure.cause),
        failure_category=failure.category,
    )
