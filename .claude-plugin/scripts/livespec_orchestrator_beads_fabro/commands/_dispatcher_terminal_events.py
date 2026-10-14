"""Read needs-human evidence from Fabro's stage lifecycle events.

A script's emitted output survives in its stage.failed failure.message, even
when the run conclusion only says the terminal has no outgoing fail edge.
Read that field, never command.started's script source (which contains every
sentinel by construction). The port has already normalized the event stream.
"""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID

__all__: list[str] = [
    "terminal_event_output",
]


def terminal_event_output(*, payload: object | None) -> str:
    """The latest terminal stage's emitted sentinel lines, or no observation."""
    output = ""
    if not isinstance(payload, list):
        return output
    for raw in cast("list[object]", payload):
        if not isinstance(raw, dict):
            continue
        event = cast("dict[str, object]", raw)
        properties = _mapping(value=event.get("properties"))
        name = event.get("event", event.get("name", event.get("event_name", event.get("type"))))
        node = event.get("node_id", properties.get("node_id"))
        if not isinstance(name, str) or not name.endswith("stage.failed"):
            continue
        if node != ESCALATION_NODE_ID:
            continue
        failure = _mapping(value=properties.get("failure", event.get("failure")))
        message = failure.get("message")
        if isinstance(message, str):
            output = "\n".join(
                line for line in message.splitlines() if line.startswith(NEEDS_HUMAN_MARKER)
            )
    return output


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
