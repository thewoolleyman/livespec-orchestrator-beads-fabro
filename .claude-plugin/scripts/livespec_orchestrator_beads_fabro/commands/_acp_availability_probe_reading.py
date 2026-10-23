"""Reading ONE ended confirmation turn off the factory's own records.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry". Split out of
`_acp_availability_probe_run` by cohesion: that module owns the TURN's
lifecycle -- launch it, bound it, reap unfinished work, assemble the records it
leaves -- while this owns the narrower question of what the factory's own
records say about a turn that has already ended. Nothing here launches,
terminates or decides what an ending MEANS.

THE SPLIT IS A SINGLE ACCOUNT RATHER THAN A SECOND ONE. There is exactly one
reading of an ended probe run, and the run module composes it; a second copy
would be two readings of one run that can disagree about whether it confirmed,
with each copy producing a well-formed answer and nothing announcing the
divergence.

THE PROMPT BOUNDARY IS READ FROM THE EVENT AND NOT FROM A PARSED CHAIN START.
`scan_acp_events` requires `candidate_index` and `primary_generation` before it
will admit an `agent.acp.started`, deliberately, because its own consumer must
not assume which candidate ran. This read asks a strictly weaker question --
did the attempt cross the prompt boundary at all -- which the adapter-launch
clause answers from the event's PRESENCE, so a pre-chain engine's start still
tells a created session from an adapter that exited before the protocol.

BOTH ENGINE GENERATIONS ARE READ WITHOUT CONSULTING THE NODE ID DIRECTLY. The
pinned engine answers from a checkpoint's `node_outcomes` keyed on the node id
while the Petri era keys its `stages` map `confirm@1`, so every comparison goes
through `fabro_stage_node`: comparing the node id against the raw key silently
matched nothing, which is the one reading that would report every successful
probe as unconfirmed.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_availability_probe import (
    AVAILABILITY_PROBE_NODE,
)
from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_outcome import (
    AcpProbeObservation,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import ACP_STARTED_EVENT
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
    fabro_run_summaries_from_payload,
)

__all__: list[str] = [
    "PROBE_READ_TIMEOUT_SECONDS",
    "probe_run_observation",
]

# The statuses that are a run CANCELLATION, both spellings the engine uses.
_CANCELLED_STATUS_KINDS: frozenset[str] = frozenset({"cancelled", "canceled"})
_SUCCEEDED_STATUS = "succeeded"

# Generous for one `inspect`, `events` or `rm` against a reachable factory, and
# bounded so an unresponsive one leaves the probe unconfirmed instead of
# holding the evaluation open. It is NOT the probe's own bound: that governs
# the TURN, and these are reads about a turn that has already ended.
PROBE_READ_TIMEOUT_SECONDS = 60.0


def probe_run_observation(
    *, port: FabroPort, run_id: str | None
) -> tuple[AcpProbeObservation, int | None]:
    """Read one ended probe run, as `(observation, cost)`.

    A launch whose run id could not be read is observed as a PROCESS EXIT with
    no cost, which is the honest reading: no run was named, so no turn
    completed, no session was recorded and nothing refused anything.
    """
    if run_id is None:
        return (
            AcpProbeObservation(
                turn_completed=False,
                acp_started=False,
                cancelled=False,
                timed_out=False,
                failure=None,
            ),
            None,
        )
    inspected = port.inspect(run_id=run_id, timeout_seconds=PROBE_READ_TIMEOUT_SECONDS)
    events = port.events(run_id=run_id, timeout_seconds=PROBE_READ_TIMEOUT_SECONDS)
    record = fabro_inspect_record(payload=inspected.payload)
    return (
        AcpProbeObservation(
            turn_completed=_turn_completed(record=record),
            acp_started=_acp_started(payload=events.payload),
            cancelled=(inspected.status_kind or "") in _CANCELLED_STATUS_KINDS,
            timed_out=False,
            failure=inspected.failure,
        ),
        _cost(payload=inspected.payload),
    )


def _turn_completed(*, record: dict[str, Any] | None) -> bool:
    """Whether the factory recorded the probe node's own attempt as SUCCEEDED.

    Keyed through `fabro_stage_node`, so a Petri-era visit-qualified stage key
    (`confirm@1`) and a pinned-engine node id both resolve: comparing the node
    id against the raw key silently matched nothing, which is the one reading
    that would report every successful probe as unconfirmed.
    """
    if record is None:
        return False
    outcomes = fabro_node_outcomes(record=record, checkpoint=_newest_checkpoint(record=record))
    return any(
        fabro_stage_node(stage=stage) == AVAILABILITY_PROBE_NODE
        and outcome.get("status") == _SUCCEEDED_STATUS
        for stage, outcome in outcomes.items()
    )


def _newest_checkpoint(*, record: dict[str, Any]) -> dict[str, Any]:
    """The newest checkpoint this record carries, or an empty one.

    Empty is what sends `fabro_node_outcomes` to the record's own `stages` map,
    which is the Petri-era shape; a pinned-engine record answers from its
    checkpoint instead. One reading serves both.
    """
    raw = record.get("checkpoints")
    if not isinstance(raw, list):
        return {}
    entries: list[dict[str, Any]] = [
        cast("dict[str, Any]", one) for one in cast("list[object]", raw) if isinstance(one, dict)
    ]
    return entries[-1] if entries else {}


def _acp_started(*, payload: object) -> bool:
    """Whether the probe node's attempt crossed the prompt boundary.

    The EVENT's presence is the whole reading, per the module docstring: this
    asks a strictly weaker question than `scan_acp_events` does, so a pre-chain
    engine's start still answers it.
    """
    if not isinstance(payload, list):
        return False
    for entry in cast("list[object]", payload):
        if not isinstance(entry, dict):
            continue
        event = cast("dict[str, Any]", entry)
        node = event.get("node")
        if event.get("type") == ACP_STARTED_EVENT and (
            not isinstance(node, str) or fabro_stage_node(stage=node) == AVAILABILITY_PROBE_NODE
        ):
            return True
    return False


def _cost(*, payload: object) -> int | None:
    """What this probe cost, or `None` when the engine reported no figure.

    Read through the ordinary run-summary parser rather than off the record by
    hand, so a probe's cost and a dispatch's cost come from one reading. `None`
    is the ORDINARY answer on this fleet -- the engine's `total_usd_micros` is
    null on every run of the pinned build -- which is exactly why the clause
    says "where observable" and both records state the observability.
    """
    summaries = fabro_run_summaries_from_payload(payload=payload)
    return summaries[0].total_usd_micros if summaries else None
