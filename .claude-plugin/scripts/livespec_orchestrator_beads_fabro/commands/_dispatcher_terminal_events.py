"""Read needs-human evidence from Fabro's stage lifecycle records.

A script's emitted output survives in its stage.failed failure.message, even
when the run conclusion only says the terminal has no outgoing fail edge.
Read that field, never command.started's script source (which contains every
sentinel by construction). The port has already normalized the event stream.

The checkpoint identifies the current failed predecessor. Its own failure
block wins over historical events; when it carries no cause, that stage's
latest failure event supplies the message. The terminal's failure and an
unrelated stage's old failure can never substitute for that observation.
"""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroFailureDetail,
    fabro_failure_detail_from_payload,
    fabro_inspect_record,
)

__all__: list[str] = [
    "routing_stage_failure",
    "terminal_event_output",
]


def terminal_event_output(*, payload: object | None) -> str:
    """The latest terminal stage's emitted sentinel lines, or no observation."""
    failures = _stage_failures(payload=payload, node=ESCALATION_NODE_ID)
    if not failures:
        return ""
    message = failures[-1].get("message")
    if not isinstance(message, str):
        return ""
    return "\n".join(line for line in message.splitlines() if line.startswith(NEEDS_HUMAN_MARKER))


def routing_stage_failure(
    *,
    inspect_payload: object | None,
    events_payload: object | None,
    stage: str,
) -> FabroFailureDetail | None:
    """Read the current failed predecessor's cause, never the run-level wrapper.

    `stage` comes from the terminal checkpoint's causal verdict, which excludes
    recovered nodes and orders failed nodes by the engine's completed order.
    Missing stage evidence stays unknown; falling back to the run conclusion
    would attribute the terminal's deliberate failure to its predecessor.
    """
    if stage == ESCALATION_NODE_ID:
        return None
    checkpoint = _checkpoint_failure(payload=inspect_payload, stage=stage)
    if checkpoint is not None and checkpoint.cause is not None:
        return checkpoint
    failures = _stage_failures(payload=events_payload, node=stage)
    if not failures:
        return checkpoint
    return _failure_detail(block=failures[-1]) or checkpoint


def _checkpoint_failure(*, payload: object | None, stage: str) -> FabroFailureDetail | None:
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    for checkpoint in reversed(fabro_inspect_checkpoints(record=record)):
        outcomes = _mapping(value=checkpoint.get("node_outcomes"))
        if stage in outcomes:
            outcome = _mapping(value=outcomes[stage])
            return _failure_detail(block=_mapping(value=outcome.get("failure")))
    return None


def _failure_detail(*, block: dict[str, object]) -> FabroFailureDetail | None:
    """Adapt a stage's direct message to the shared cause-chain classifier.

    Stage failures carry `message` directly; the run-conclusion reader knows
    `detail.message`. Keep causes, category and signature intact so provider
    limits still take the same classification path and retain their vendor.
    """
    normalized = dict(block)
    message = block.get("message")
    if isinstance(message, str):
        normalized["detail"] = {"message": message, "category": block.get("category")}
    return fabro_failure_detail_from_payload(payload={"failure": normalized})


def _stage_failures(*, payload: object | None, node: str) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, list):
        return ()
    failures: list[dict[str, object]] = []
    for raw in cast("list[object]", payload):
        if not isinstance(raw, dict):
            continue
        event = cast("dict[str, object]", raw)
        properties = _mapping(value=event.get("properties"))
        name = event.get("event", event.get("name", event.get("event_name", event.get("type"))))
        event_node = event.get("node_id", properties.get("node_id"))
        if not isinstance(name, str) or not name.endswith("stage.failed"):
            continue
        if event_node != node:
            continue
        failures.append(_mapping(value=properties.get("failure", event.get("failure"))))
    return tuple(failures)


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
