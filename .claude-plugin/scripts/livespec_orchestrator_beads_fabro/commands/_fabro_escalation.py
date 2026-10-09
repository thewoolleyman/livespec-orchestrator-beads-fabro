"""Engine-escalation tells read off a `fabro inspect --json` run record.

A run that ends at the workflow's `escalate` node got there one of two ways,
and the operator needs to be told WHICH:

- an AGENT reported a structured needs-human ending, so a question genuinely
  awaits an answer and attaching to the run is the answer path; or
- the ENGINE classified a node failure as non-retryable and routed the run to
  the escalation node itself. No agent asked anything, the retry budget is
  already spent, and attaching cannot clear it.

The terminal STATUS cannot tell them apart — both park as `blocked` /
`human_input_required` — so the discriminator is the pair of tells this module
reads off the newest checkpoint: `next_node_id` naming the escalation node,
PLUS a recorded `loop_failure_signatures` map, which only a node failure the
loop actually recorded can produce. The engine-routed case is the only one
carrying both; an agent-reported ending rides an ordinary conditional edge off
a node that SUCCEEDED, so it records no loop failure signature.

MEASURED, run 01M10CYZ8S9TNPZ2MW096NJW7V (work-item bd-ib-utq7b4), 2026-08-27,
parsed structurally rather than grepped:

    checkpoints[4].checkpoint.next_node_id            = "escalate"
    checkpoints[4].checkpoint.loop_failure_signatures =
        {"review|deterministic|acp turn failed": 1}

Reading these two fields is deliberately the CHEAP discriminator. The only
other way to tell an engine escalation from a genuine gate is to dump the ACP
adapter's stderr, which needs adapter knowledge and reasoning about which ACP
backend was in play; this one needs neither.

This module reads the run record and NOTHING ELSE: the engine's own routing is
correct and is not re-derived or second-guessed here. The defect it exists to
fix is the Dispatcher's RENDERING of that accurate state, not its
classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = [
    "ESCALATION_NODE_ID",
    "FabroEscalation",
    "fabro_escalation_from_payload",
]

# The `needs_human` terminal node id in
# `.fabro/workflows/implement-work-item/workflow.fabro` (it replaced the
# `escalate` hexagon under plan ledger-is-the-only-gate). Keep the two in
# lockstep: renaming the node there without renaming it here silently loses
# the engine-escalation rendering.
ESCALATION_NODE_ID = "needs_human"


@dataclass(frozen=True, kw_only=True)
class FabroEscalation:
    """An engine-routed escalation, read off a run record's newest checkpoint."""

    next_node_id: str
    loop_failure_signatures: tuple[str, ...]


def fabro_escalation_from_payload(*, payload: object | None) -> FabroEscalation | None:
    """Return the escalation tells, or None when the run is not engine-escalated.

    None covers every non-escalated shape: an unusable payload, a checkpoint
    routing somewhere other than the escalation node, and — the case that keeps
    a genuine human gate reading as a human gate — a run routed to the
    escalation node with NO loop failure signature recorded, which is what an
    agent-reported needs-human ending looks like.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    next_node_id: str | None = None
    signatures: tuple[str, ...] = ()
    for checkpoint in fabro_inspect_checkpoints(record=record):
        candidate: object = checkpoint.get("next_node_id")
        if isinstance(candidate, str) and candidate.strip():
            next_node_id = candidate
            signatures = _signatures(value=checkpoint.get("loop_failure_signatures"))
    if next_node_id != ESCALATION_NODE_ID or not signatures:
        return None
    return FabroEscalation(next_node_id=next_node_id, loop_failure_signatures=signatures)


def _signatures(*, value: object) -> tuple[str, ...]:
    """The recorded loop failure signatures, sorted for a stable rendering.

    The field is a signature→count map; only the signatures are carried,
    because the operator-facing message names WHAT failed, not how often the
    loop counted it.
    """
    if not isinstance(value, dict):
        return ()
    mapping = cast("dict[object, object]", value)
    return tuple(sorted(key for key in mapping if isinstance(key, str) and key.strip()))
