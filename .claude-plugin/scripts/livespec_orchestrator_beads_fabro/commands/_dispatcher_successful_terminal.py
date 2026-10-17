"""Structured checkpoint evidence for a successful route behind run-store loss."""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = [
    "successful_store_loss_checkpoint",
]

_RUN_STORE_LOSS_MESSAGE = "Worker exited before emitting a terminal run event: exit status: 0"


def successful_store_loss_checkpoint(
    *,
    run_id: str | None,
    inspect: FabroInspectResult | None,
) -> bool:
    """Recognize the incident's last durable successful checkpoint.

    The engine's own conclusion says the worker exited before persisting a
    terminal run event, so it cannot answer whether the workflow completed.
    The newest STRUCTURED checkpoint for THIS run can: it names the stage the
    run reached, the node it selected next, and that stage's own outcome. A
    checkpoint belonging to another run, a conclusion whose cause is anything
    but the run-store loss, and an inspection that could not be taken are all
    read as no evidence rather than as success.
    """
    record = None if inspect is None else fabro_inspect_record(payload=inspect.payload)
    checkpoints = () if record is None else fabro_inspect_checkpoints(record=record)
    checkpoint: dict[str, Any] = {} if not checkpoints else checkpoints[-1]
    outcomes_raw: object = checkpoint.get("node_outcomes")
    outcomes = cast("dict[object, object]", outcomes_raw) if isinstance(outcomes_raw, dict) else {}
    final_raw: object = outcomes.get("verify_pr")
    final = cast("dict[object, object]", final_raw) if isinstance(final_raw, dict) else {}
    failure = None if inspect is None else inspect.failure
    return bool(
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
        and isinstance(checkpoint.get("git_commit_sha"), str)
    )
