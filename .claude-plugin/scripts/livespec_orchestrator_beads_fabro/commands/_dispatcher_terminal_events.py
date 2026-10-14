"""Read needs-human evidence from Fabro's stage lifecycle records.

A script's emitted output survives in its stage.failed failure block, even when
the run conclusion only says the terminal has no outgoing fail edge. WHICH
field of that block carries it is an engine fact rather than a constant — the
pinned engine writes a `causes` chain, the Petri-era engine one `detail.message`
— so every text channel the block offers is read. Never read
command.started's script source, which contains every sentinel by
construction. The port has already normalized the event stream.

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
    """The latest terminal stage's emitted sentinel lines, or no observation.

    EVERY CHANNEL A STAGE FAILURE CAN CARRY TEXT ON IS READ, for the same
    shape-robustness reason `routing_stage_failure` routes its block through
    `fabro_failure_detail_from_payload`. The PINNED engine carries a stage's
    emitted output as a `causes` CHAIN behind the fixed `ACP protocol error`
    wrapper, with the block's top-level `message` saying only `ACP turn failed`
    (`plan/pr-stage-backgrounded-push-fault/research/001-...-2026-10-08.md`
    measured the terminal's own preservation line arriving exactly there); the
    PETRI-era engine carries no chain at all and puts that text in one
    `detail.message` (research note 007, probes p2 and p6). A reader of
    `message` alone was therefore incapable of returning a hit on the engine
    this defect was measured on, and its clean empty answer is indistinguishable
    from a terminal that preserved nothing.

    The scan is a UNION rather than a preference, which is where it parts
    company with the cause read beside it: that one SELECTS a single fault and
    so must let the real chain win, while this one is looking for a line some
    channel happens to carry and has no basis for ranking the channels. A line
    the engine wrote to two of them is reported ONCE, because a 0.254 block
    carries both and a duplicated ref reads as two preservation claims.
    """
    failures = _stage_failures(payload=payload, node=ESCALATION_NODE_ID)
    if not failures:
        return ""
    return "\n".join(_sentinel_lines(block=failures[-1]))


def _sentinel_lines(*, block: dict[str, object]) -> tuple[str, ...]:
    """Every sentinel line the block emitted, in channel order, deduplicated.

    A line must START with the marker: the engine's own prose quotes a node's
    script, so a matched substring would let a `command.started` script source —
    which contains every sentinel by construction — reach this reader through a
    failure message that merely echoes it.
    """
    lines: list[str] = []
    for text in _emitted_texts(block=block):
        for line in text.splitlines():
            if line.startswith(NEEDS_HUMAN_MARKER) and line not in lines:
                lines.append(line)
    return tuple(lines)


def _emitted_texts(*, block: dict[str, object]) -> tuple[str, ...]:
    """The block's three text channels, as the engines write them.

    A non-text value on any one of them contributes nothing rather than a
    rendering of itself, and never suppresses the others: an unmeasured shape on
    one channel says nothing about what the next channel carries.
    """
    candidates: list[object] = [block.get("message")]
    causes = block.get("causes")
    if isinstance(causes, list):
        candidates.extend(cast("list[object]", causes))
    candidates.append(_mapping(value=block.get("detail")).get("message"))
    return tuple(value for value in candidates if isinstance(value, str))


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
