"""Reading ONE operator clearance off the factory run record that carries it.

The READ half of the factory-native clearance record, and the counterpart of
`_acp_clearance_factory_record`'s write. `_acp_clearance_records` owns the
record's SHAPE and the line-level parse; this module owns the one thing neither
of them can: where in a factory run's own `inspect` record that line is found.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" requires an operator clearance to be recorded "by a minimal
factory-native record whose recorded outcome carries the clearance's exact
identity, actor, time, and reason -- so retirement is reconstructible from the
same source as observation". This is the reconstruction: a peer repository's
Dispatcher, which has no access to the clearing repository's journal and never
saw the operator's invocation, recovers the clearance from the factory alone.

TWO OUTCOME MAPS, BECAUSE THE TWO ENGINES RECORD A NODE'S OUTCOME IN DIFFERENT
PLACES, and `_fabro_port_node_outcomes` records the measurement: the Petri-era
build writes the record's own top-level `stages` map, keyed `<node>@<visit>`,
each entry carrying `handler`, `state`, `output` and `response`; the pinned
build writes its checkpoint's `node_outcomes`. Reading one and not the other
answers `None` on the other engine -- and at the evidence surface a `None` is
indistinguishable from a run that recorded no clearance, so the clearance would
simply never be observed on half the fleet.

BOTH MAPS ARE SCANNED RATHER THAN SELECTED BETWEEN, and the node id is not
consulted at all. A record carries at most one clearance line by construction
(the graph has one script node), the line carries its own marker, and the two
engines spell the node key differently -- `record` against `002-record@1` --
so a reader keying on the id would have to re-derive that division for no gain.
The MARKER is what decides, which is the same discipline `_acp_clearance_records`
applies one level down.

NOTHING HERE IS A DECISION. It answers what one record SAYS; whether that
clearance retires anything belongs to `_acp_hold_retirement`, where the
clearance and the records it addresses are in hand together.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_clearance_records import (
    AcpHoldClearance,
    clearance_from_outcome,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record

__all__: list[str] = [
    "recorded_clearance",
]

# The field a node outcome records its own output under, identical on both
# engines' maps -- which is what lets one scan serve both.
_OUTPUT_FIELD = "output"


def recorded_clearance(*, payload: object) -> AcpHoldClearance | None:
    """The clearance one run's recorded outcome states, or `None` for none.

    `None` covers every way this is not a clearance record, and they are
    deliberately not distinguished: a row reaches here only because its
    LISTING LABELS already marked it as one, so an unreadable payload, a record
    with no outcome map and an outcome carrying ordinary prose are all the same
    answer -- this read established no clearance. Retirement is the
    destructive direction, so the record simply stands.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    for text in _recorded_outputs(record=record):
        clearance = clearance_from_outcome(text=text)
        if clearance is not None:
            return clearance
    return None


def _recorded_outputs(*, record: Mapping[str, Any]) -> tuple[str, ...]:
    """Every recorded output text on this record, whichever engine wrote it."""
    checkpoint = _entries(raw=record.get("checkpoint"))
    outputs: list[str] = []
    for key in (record.get("stages"), checkpoint.get("node_outcomes")):
        for entry in _entries(raw=key).values():
            output = _entries(raw=entry).get(_OUTPUT_FIELD)
            if isinstance(output, str):
                outputs.append(output)
    return tuple(outputs)


def _entries(*, raw: object) -> dict[str, Any]:
    """One engine-written mapping as a typed dict, or an empty one.

    Shared by all three levels of the walk above -- the checkpoint, each
    outcome map and each entry -- so a record whose shape is unusable at ANY
    level degrades the same way rather than raising from whichever level
    happened to be reached first.
    """
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in cast("dict[Any, Any]", raw).items()}
