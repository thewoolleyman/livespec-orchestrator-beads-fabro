"""Read needs-human evidence from Fabro's stage lifecycle records.

A script's emitted output survives in its stage.failed failure.message, even
when the run conclusion only says the terminal has no outgoing fail edge.
Read that field, never command.started's script source (which contains every
sentinel by construction). The port has already normalized the event stream.

THE RUN CONCLUSION IS THE WRONG PLACE TO ASK WHY A RUN WAS ROUTED HERE, and
that is the second reading this module exists for. `needs_human` is a dead-end
script that exits 1 by design, so on an engine-routed ending the conclusion's
own innermost cause is the terminal's `stage needs_human failed with no
outgoing fail edge` — a sentence that names the graph's shape and no fault.
The routing stage's own failure message is the one line a triager needs, and
it survives only on the stage records below.

THE CURRENT FAILED PREDECESSOR'S OWN FAILURE BLOCK WINS over its historical
events. The checkpoint is the engine's account of the ending; an event is an
account of one attempt, and a node the bounded fix loop retried has older
events that describe a failure the run went on to survive. The event stream is
consulted only where the checkpoint carries no cause, which is the shape the
pinned engine writes when it records a status and no detail.

WHAT THE STAGE READ MAY NOT REPLACE IS THE PROVIDER ATTRIBUTION. By the time
this runs, `_fabro_executed_candidate` may already have re-attributed the
observed ceiling from the run's own labels, which is the only reading that
tells Claude's and Codex's shared "You've hit your usage limit" literal apart.
Re-deriving the vendor from the routing stage's cause text would discard that
correction and name whichever vendor the message happens to resemble — the
exact misattribution that reading exists to retire — so an observed ceiling's
provider and entitlement are carried through unchanged, and an unreadable
routing stage retracts the CAUSE without retracting the ceiling. A dropped
ceiling writes no dispatcher-owned hold, and the next dispatch burns the same
exhausted credential.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import graph_node_id
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
    observed: FabroFailureDetail | None,
    inspect_payload: object | None,
    events_payload: object | None,
    stage: str,
) -> FabroFailureDetail | None:
    """What the stage that routed this run to the terminal recorded, if anything.

    `stage` comes from the terminal checkpoint's causal verdict, which already
    excludes recovered nodes and orders the failed ones by the engine's own
    completed order. The terminal itself is refused outright: it is the one
    node that cannot be the cause, and attributing its deliberate exit-1 is the
    whole defect being closed.

    A stage whose failure NOTHING records leaves the cause UNKNOWN rather than
    falling back to the run conclusion. The conclusion is where the terminal's
    own failure lives, so the fallback would report the exact sentence this
    reader exists to suppress — and would report it indistinguishably from a
    genuine attribution.
    """
    routed = (
        None
        if stage == ESCALATION_NODE_ID
        else _routed_failure(
            inspect_payload=inspect_payload,
            events_payload=events_payload,
            stage=stage,
        )
    )
    return _carrying_observed_ceiling(routed=routed, observed=observed)


def _routed_failure(
    *,
    inspect_payload: object | None,
    events_payload: object | None,
    stage: str,
) -> FabroFailureDetail | None:
    """One stage's own failure, checkpoint first and its events as the fallback."""
    checkpoint = _checkpoint_failure(payload=inspect_payload, stage=stage)
    if checkpoint is not None and checkpoint.cause is not None:
        return checkpoint
    failures = _stage_failures(payload=events_payload, node=stage)
    if not failures:
        return checkpoint
    return _failure_detail(block=failures[-1]) or checkpoint


def _carrying_observed_ceiling(
    *,
    routed: FabroFailureDetail | None,
    observed: FabroFailureDetail | None,
) -> FabroFailureDetail | None:
    """Keep a provider ceiling the observation established, whatever the stage said.

    A ceiling is a fact about the RUN, so failing to name the stage that hit it
    is no reason to stop holding the credential. The observation's provider and
    entitlement win over the routed read's own classification because only the
    observation can have been re-attributed from the run's labels; where the
    observation records no ceiling, the routed read's classification stands and
    may newly find one the conclusion's winning block never carried.
    """
    if observed is None or not observed.provider_usage_limit:
        return routed
    if routed is None:
        return replace(observed, cause=None, category=None, signature=None)
    return replace(
        routed,
        provider_usage_limit=True,
        provider_usage_limit_provider=observed.provider_usage_limit_provider,
        provider_usage_limit_entitlement=observed.provider_usage_limit_entitlement,
    )


def _checkpoint_failure(*, payload: object | None, stage: str) -> FabroFailureDetail | None:
    """The newest checkpoint that records an outcome for `stage`, read for its failure.

    The map is keyed by whatever the engine spelled, so the lookup is exact
    rather than normalized: `stage` was itself taken off one of these maps.
    """
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

    A stage failure carries its text in `message`, while the conclusion reader
    knows `causes` and `detail.message`. Presenting the message as a `detail`
    is what routes it through the ONE classification pass that decides whether
    a fault is permanent and which vendor refused — a second, parallel pass
    here would be a second place for those two verdicts to disagree, and both
    would look well-formed while they did. Causes, category and signature ride
    along untouched so a block carrying a real chain keeps it.
    """
    normalized = dict(block)
    message = block.get("message")
    if isinstance(message, str):
        normalized["detail"] = {"message": message, "category": block.get("category")}
    return fabro_failure_detail_from_payload(payload={"failure": normalized})


def _stage_failures(*, payload: object | None, node: str) -> tuple[dict[str, object], ...]:
    """Every stage.failed failure block one node recorded, oldest first.

    The node match is normalized on BOTH sides because the two engines spell a
    stage differently: the pinned engine keys its outcome map `implement` while
    the Petri-era engine keys its stage map `002-implement@1`, and the event
    stream carries the bare graph node id on either. A direct comparison
    therefore cannot match a Petri-derived `stage` against any event it was
    looking for, and would report a clean, plausible "this node recorded
    nothing" for a node whose failure is right there.
    """
    if not isinstance(payload, list):
        return ()
    wanted = graph_node_id(node=node)
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
        if not isinstance(event_node, str) or graph_node_id(node=event_node) != wanted:
            continue
        failures.append(_mapping(value=properties.get("failure", event.get("failure"))))
    return tuple(failures)


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
