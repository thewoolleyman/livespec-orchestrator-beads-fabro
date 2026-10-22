"""What one dispatch's OWN selection record evidences about the run it launched.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": fallback selection "is observed from the Dispatcher's own decisions"
and reconciliation replays "selection-to-execution observation idempotently
using factory, run, node attempt and selection identity". The Dispatcher
renders ONE adapter per node, so no engine failover event can fire and the
warning lifecycle cannot be sourced from one; these two readings are the
Dispatcher-side replacements, and they are deliberately the same shape so one
join serves both:

- a node whose selection rendered a NON-PRIMARY candidate, and whose run then
  executed that node, is a model-fallback WARNING;
- a node whose selection rendered the PRIMARY, and whose run executed it
  SUCCESSFULLY, is the primary attempt that can retire one.

SPLIT OUT OF `_acp_fallback_warning_ledger` BY COHESION. That module folds the
ledger and owns the retirement RULE -- which attempt clears which warning, and
which replacement supersedes one -- while this owns the EVIDENCE one selection
record plus one run's outcomes supply. The ledger imports both public entry
points back, so its own surface is unchanged and the two concerns are readable
apart; the rule is what both sources of evidence share, which is why the rule
stayed where it was and the evidence moved.

THE OUTCOME MAP IS TRI-STATE AND THE THIRD STATE IS LOAD-BEARING. `None` says
the run's node outcomes could not be READ, which is not the same answer as a
node the run never reached: `_fabro_port_node_outcomes` records that the Petri
engine writes no `node_outcomes` at all, so an empty map means a record
offering nothing to grade. Collapsing it onto "nothing executed" would read
every unreadable run as evidence that no fallback ran, which is the direction
that erases a standing warning on the strength of a failed read.

THE OUTCOME KEYS ARE VISIT-QUALIFIED AND A SELECTION'S ARE NOT. Petri keys its
stage map `<node>@<visit>`, and the port returns those keys as the engine wrote
them because one caller renders that half. A selection record names the
CONFIGURED node, so comparing the two directly matches nothing -- and matching
nothing is SILENT: every warning stays unminted and the attention lane reads as
a repository where no fallback has ever run. The division is the port's own
`fabro_stage_node`, so this reading and the port's own collapse cannot disagree
about where a node id ends. After that collapse the projection is one-to-one,
which is what makes re-keying by node safe here rather than a merge of two
readings of one node.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    MODEL_FALLBACK_SCHEMA_VERSION,
    MODEL_FALLBACK_STAGE,
    AcpPrimaryAttempt,
    warning_id,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    ACP_NODE_SELECTION_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import (
    STAMP_JOURNAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_stage_node,
)

__all__: list[str] = [
    "selection_primary_attempts",
    "selection_warning_records",
]

# The one node status either engine's outcome map spells for a node that
# finished its work. Read exactly as `_dispatcher_successful_terminal` reads
# it, so "this node succeeded" has one meaning across the package.
_SUCCEEDED = "succeeded"

# The cause a selection-derived warning records. It is not a provider's typed
# availability cause, because no provider refused anything here: the Dispatcher
# itself chose the position, and saying so is what keeps this record from
# reading as a vendor outage nobody observed.
_SELECTION_CAUSE = "dispatcher-selection"
_NODE_SCOPE = "node"


@dataclass(frozen=True, kw_only=True)
class _ExecutedSelection:
    """One node this run both SELECTED and EXECUTED, with its graded outcome.

    The joined pair, carried rather than re-derived per reading, because the
    two public entry points below must agree about which nodes a run executed:
    two walks of one selection record would be two populations, and a
    divergence between them would surface as a warning minted for a node whose
    primary attempt the other reading had already cleared.
    """

    node: str
    choice: Mapping[object, object]
    occurred_at: str
    outcome: Mapping[str, object]


def selection_warning_records(
    *,
    records: tuple[Mapping[str, object], ...],
    work_item_id: str,
    run_id: str,
    outcomes: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], ...] | None:
    """Build warnings from executed non-primary Dispatcher selections.

    An empty outcome map is unavailable evidence, not proof that every selected
    node was skipped. Returning `None` lets the caller retain the existing
    warning and schedule another read.
    """
    executed = _executed_selections(
        records=records, work_item_id=work_item_id, run_id=run_id, outcomes=outcomes
    )
    if executed is None:
        return None
    minted = (
        _selection_warning(one=one, work_item_id=work_item_id, run_id=run_id) for one in executed
    )
    return tuple(warning for warning in minted if warning is not None)


def selection_primary_attempts(
    *,
    records: tuple[Mapping[str, object], ...],
    work_item_id: str,
    run_id: str,
    outcomes: Mapping[str, Mapping[str, object]],
) -> tuple[AcpPrimaryAttempt, ...] | None:
    """The primary attempts this run's own selection evidences, or `None`.

    The clearance half of the same join. `None` carries the identical meaning
    it does above -- the outcomes could not be read -- which is what keeps an
    unreadable run from clearing a warning as well as from minting one.
    """
    executed = _executed_selections(
        records=records, work_item_id=work_item_id, run_id=run_id, outcomes=outcomes
    )
    if executed is None:
        return None
    graded = (_primary_attempt(one=one) for one in executed)
    return tuple(attempt for attempt in graded if attempt is not None)


def _executed_selections(
    *,
    records: tuple[Mapping[str, object], ...],
    work_item_id: str,
    run_id: str,
    outcomes: Mapping[str, Mapping[str, object]],
) -> tuple[_ExecutedSelection, ...] | None:
    """Join this run's own selection to the nodes its outcomes say it executed.

    `None` is unavailable evidence; the EMPTY tuple is a selection that joins
    to no executed node, which is an ordinary answer -- an unexecuted preflight
    selection for a node the run never reached owes no record of either kind.
    """
    if not outcomes:
        return None
    selection = _latest_selection(records=records, work_item_id=work_item_id, run_id=run_id)
    if selection is None:
        return ()
    occurred_at = _text(value=selection.get("at"))
    choices = selection.get("selections")
    if occurred_at is None or not isinstance(choices, Mapping):
        return ()
    graded = {fabro_stage_node(stage=stage): outcome for stage, outcome in outcomes.items()}
    found: list[_ExecutedSelection] = []
    for node, raw in cast("Mapping[object, object]", choices).items():
        if not isinstance(node, str) or node not in graded or not isinstance(raw, Mapping):
            continue
        found.append(
            _ExecutedSelection(
                node=node,
                choice=cast("Mapping[object, object]", raw),
                occurred_at=occurred_at,
                outcome=graded[node],
            )
        )
    return tuple(found)


def _latest_selection(
    *, records: tuple[Mapping[str, object], ...], work_item_id: str, run_id: str
) -> Mapping[str, object] | None:
    """Return this run's selection, joined through its immutable dispatch id.

    Historical rows predate dispatch correlation, so they remain readable only
    when this run has no stamp at all.  Once a run is stamped, a selection that
    does not carry the same id is deliberately not evidence for that run.
    """
    stamps = tuple(
        record
        for record in records
        if record.get("stage") == STAMP_JOURNAL_STAGE
        and record.get("work_item_id") == work_item_id
        and record.get("run_id") == run_id
    )
    dispatch_ids = {
        dispatch_id
        for record in stamps
        if (dispatch_id := _text(value=record.get("dispatch_id"))) is not None
    }
    for record in reversed(records):
        if (
            record.get("stage") != ACP_NODE_SELECTION_STAGE
            or record.get("work_item_id") != work_item_id
        ):
            continue
        dispatch_id = _text(value=record.get("dispatch_id"))
        if dispatch_id in dispatch_ids or (not stamps and dispatch_id is None):
            return record
    return None


def _selection_warning(
    *, one: _ExecutedSelection, work_item_id: str, run_id: str
) -> dict[str, object] | None:
    """Translate one executed non-primary selection into the legacy record shape."""
    index = one.choice.get("selected_index")
    if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
        return None
    selection_identity = _text(value=one.choice.get("selection_identity"))
    candidate_key = _text(value=one.choice.get("selected_candidate_key"))
    availability_key = _text(value=one.choice.get("selected_availability_key"))
    primary_generation = _text(value=one.choice.get("primary_generation_digest"))
    full_chain = _text(value=one.choice.get("full_chain_digest"))
    if None in (
        selection_identity,
        candidate_key,
        availability_key,
        primary_generation,
        full_chain,
    ):
        return None
    event_id = f"selection:{run_id}:{selection_identity}"
    return {
        "stage": MODEL_FALLBACK_STAGE,
        "schema_version": MODEL_FALLBACK_SCHEMA_VERSION,
        "warning_id": warning_id(event_id=event_id, node=one.node),
        "node": one.node,
        "occurred_at": one.occurred_at,
        "candidate_display_name": candidate_key,
        "candidate_key": candidate_key,
        "candidate_index": index,
        "availability_key": availability_key,
        "hold_key": availability_key,
        "cause": _SELECTION_CAUSE,
        "scope": _NODE_SCOPE,
        "primary_generation": primary_generation,
        "full_chain": full_chain,
        "event_id": event_id,
        "work_item_id": work_item_id,
    }


def _primary_attempt(*, one: _ExecutedSelection) -> AcpPrimaryAttempt | None:
    """One executed PRIMARY selection as the clearance rule's attempt, else `None`.

    `executed` is `True` unconditionally, and that is a statement about where
    this value came from rather than an assumption: reaching here means the
    RUN'S OWN outcome map graded this node, and a credential probe or an
    unexecuted preflight selection appears in no such map at all. The two
    near-misses that field exists to refuse therefore arrive as data rather
    than as a special case, exactly as they do for the event-sourced reading.
    """
    index = one.choice.get("selected_index")
    if isinstance(index, bool) or not isinstance(index, int) or index != 0:
        return None
    primary_generation = _text(value=one.choice.get("primary_generation_digest"))
    if primary_generation is None:
        return None
    return AcpPrimaryAttempt(
        node=one.node,
        primary_generation=primary_generation,
        started_at=one.occurred_at,
        executed=True,
        succeeded=one.outcome.get("status") == _SUCCEEDED,
    )


def _text(*, value: object) -> str | None:
    """Return a non-empty text identity, otherwise ``None``."""
    return value.strip() if isinstance(value, str) and value.strip() else None
