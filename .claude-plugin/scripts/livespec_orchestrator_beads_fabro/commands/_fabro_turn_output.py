"""The recorded output of a run's SUCCEEDED agent turns, read off its `inspect` record.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": a `turn.final_output` signature "applies only to an agent node
attempt that the engine recorded as succeeded", and "the Dispatcher MUST read
that recorded output from the run's resolved factory, exactly as it reads a
failure for the other sources". This is that read. It is a port-level leaf for
the reason `_fabro_port_node_outcomes` is: the release reading and the
retirement reading both ask it, and two copies of the walk is how they would
come to disagree about which attempts count as agent turns.

ONLY THE PETRI `stages` MAP CARRIES A TURN'S TEXT. Each entry there records
`handler`, `state`, `response` and `output`; the pinned engine's checkpoint
`node_outcomes` record a status and no text at all. So a record without that map
yields no turn, which is the conservative direction: nothing is classified from
text nobody recorded.

THE TEXT IS `response` WHEN THE ENGINE RECORDED ONE AND `output` OTHERWISE. A
measured agent entry carries an empty `response` beside a populated `output`, so
reading `response` alone would see no text on exactly the entries this exists
for. Either way the text reaches only a `turn.final_output` signature, which
matches nothing but a refusal ending the output at a sentence boundary.

THE ROUTING PREDECESSOR IS THE LAST NON-TERMINAL STAGE IN RECORD ORDER, and a
turn is returned for it only when that stage is itself a succeeded agent turn.
That is the clause's "the run reached a terminal other than its successful exit
through the reclassified attempt's own outcome ... and no later attempt of any
node ... failed" made structural: any later failed attempt, agent or not, would
BE the last stage, so the answer would be a failed stage and no turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import graph_node_id
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

__all__: list[str] = [
    "SucceededAgentTurn",
    "routing_predecessor_turn",
    "succeeded_agent_turns",
]

_AGENT_HANDLER = "agent"
_SUCCEEDED_STATE = "succeeded"


@dataclass(frozen=True, kw_only=True)
class SucceededAgentTurn:
    """One agent node attempt the engine recorded as succeeded, with its text.

    `stage` is the key as the engine wrote it, visit suffix included, and `node`
    is the graph node id the selected-identity map is keyed on. `output` is
    `None` when the record carries no text for the turn.
    """

    stage: str
    node: str
    output: str | None


def succeeded_agent_turns(*, payload: object | None) -> tuple[SucceededAgentTurn, ...]:
    """Every succeeded agent turn one record carries, newest visit per node, in order."""
    turns = (_turn(key=key, entry=entry) for key, entry in _ordered_entries(payload=payload))
    return tuple(turn for turn in turns if turn is not None)


def routing_predecessor_turn(*, payload: object | None) -> SucceededAgentTurn | None:
    """The succeeded agent turn a needs-human terminal was routed from, or `None`.

    `None` covers every other ending: no terminal was reached, the last stage
    before it failed, or it was not an agent turn.
    """
    if terminal_evidence(payload=payload) is None:
        return None
    entries = tuple(
        (key, entry)
        for key, entry in _ordered_entries(payload=payload)
        if fabro_stage_node(stage=key) != ESCALATION_NODE_ID
    )
    if not entries:
        return None
    key, entry = entries[-1]
    return _turn(key=key, entry=entry)


def _ordered_entries(*, payload: object | None) -> tuple[tuple[str, dict[str, Any]], ...]:
    """The collapsed stage keys of a Petri record paired with their raw entries."""
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return ()
    stages: object = record.get("stages")
    if not isinstance(stages, dict):
        return ()
    stage_map = cast("dict[object, object]", stages)
    checkpoints = fabro_inspect_checkpoints(record=record)
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})
    entries: list[tuple[str, dict[str, Any]]] = []
    for key in outcomes:
        entry = stage_map.get(key)
        if isinstance(entry, dict):
            entries.append((key, cast("dict[str, Any]", entry)))
    return tuple(entries)


def _turn(*, key: str, entry: dict[str, Any]) -> SucceededAgentTurn | None:
    """The turn one entry records, or `None` for any other handler or state."""
    if entry.get("handler") != _AGENT_HANDLER or entry.get("state") != _SUCCEEDED_STATE:
        return None
    return SucceededAgentTurn(stage=key, node=graph_node_id(node=key), output=_text(entry=entry))


def _text(*, entry: dict[str, Any]) -> str | None:
    """The turn's recorded text: `response` when non-blank, else `output`, else `None`."""
    for field in ("response", "output"):
        value: object = entry.get(field)
        if isinstance(value, str) and value.strip() != "":
            return value
    return None
