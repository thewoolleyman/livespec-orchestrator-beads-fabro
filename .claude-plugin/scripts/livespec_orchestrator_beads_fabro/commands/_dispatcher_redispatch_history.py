"""Read an item's completed attempts back from the factory each run was recorded on.

`SPECIFICATION/contracts.md` section "Across-dispatch required-result progress"
requires the admission valve to judge each earlier attempt by evidence read
from the factory RECORDED for that run, never from whatever server the local
default names.  The journal's `dispatch-run-stamp` rows are that record: they
pair a run id with the factory it was launched on.  A run whose factory was not
recorded, or whose record that factory no longer answers, is classified as an
unknown cause so the progress decision asks for a diagnosis instead of reading
the silence as either progress or a host failure.

Progress is the position of the furthest successfully completed node in the
workflow graph's own dependency order (breadth-first depth from its entry
nodes), never a stage name and never a retry counter.  Two attempts are
comparable only when their graphs have the same node and edge topology.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_inspect_record,
    fabro_status_kind_from_payload,
)

__all__: list[str] = [
    "RecordedRun",
    "RunReader",
    "WorkflowOrder",
    "completed_attempt",
    "recorded_runs",
    "workflow_order",
]

_STAMP_STAGE = "dispatch-run-stamp"
_DISPATCH_STAGE = "dispatch-id"
_TERMINAL_KINDS = frozenset({"succeeded", "failed", "dead", "canceled", "cancelled"})
_HOST_KINDS = frozenset({"dead", "canceled", "cancelled"})
_SUCCESS_STATUSES = frozenset({"succeeded", "success"})
_FAILED_STATUS = "failed"
_ESCALATION_NODE = "needs_human"
_NO_MILESTONE = "(none)"
_CAUSE_EXCERPT = 160
# Faults of the factory host or its sandbox driver, never of the item.  Matching
# is by substring on the engine's own cause text; an unmatched failure is NOT
# assumed to be a host fault.
_HOST_MARKERS = (
    "sandbox became unreachable",
    "database is locked",
    "exec stream ended without an exit status",
    "releasing the petri run's lease",
    "no space left on device",
    "enospc",
)


class RunReader(Protocol):
    """The one factory read this module needs: a run record from a named factory."""

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None: ...


@dataclass(frozen=True, kw_only=True)
class RecordedRun:
    """One run the journal stamped onto an item, with the factory it was launched on."""

    run_id: str
    factory: str | None
    workflow_name: str | None


@dataclass(frozen=True, kw_only=True)
class WorkflowOrder:
    """A workflow graph's topology identity and each node's dependency depth."""

    identity: str
    depth: Mapping[str, int]


def recorded_runs(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> tuple[RecordedRun, ...]:
    """The item's stamped runs, oldest first, each run id once."""
    workflows = {
        dispatch_id: name
        for record in records
        if record.get("stage") == _DISPATCH_STAGE
        and isinstance(dispatch_id := record.get("dispatch_id"), str)
        and isinstance(name := record.get("workflow_name"), str)
    }
    runs: dict[str, RecordedRun] = {}
    for record in records:
        if record.get("stage") != _STAMP_STAGE or record.get("work_item_id") != work_item_id:
            continue
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or run_id in runs:
            continue
        factory = record.get("dispatch_factory")
        dispatch_id = record.get("dispatch_id")
        runs[run_id] = RecordedRun(
            run_id=run_id,
            factory=factory if isinstance(factory, str) and factory else None,
            workflow_name=workflows.get(dispatch_id) if isinstance(dispatch_id, str) else None,
        )
    return tuple(runs.values())


def workflow_order(*, graph_text: str | None) -> WorkflowOrder | None:
    """Dependency depth of every node, or `None` when the graph cannot be read."""
    if graph_text is None:
        return None
    graph = parse_dot_graph(text=graph_text)
    if isinstance(graph, str):
        return None
    successors: dict[str, list[str]] = {}
    for edge in graph.edges:
        successors.setdefault(edge.source, []).append(edge.destination)
    destinations = {edge.destination for edge in graph.edges}
    entries = sorted(name for name in graph.nodes if name not in destinations)
    depth: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque((entry, 0) for entry in entries)
    while queue:
        node, level = queue.popleft()
        if node in depth:
            continue
        depth[node] = level
        queue.extend((following, level + 1) for following in successors.get(node, ()))
    topology = (
        "|".join(sorted(graph.nodes))
        + "#"
        + "|".join(sorted(f"{edge.source}>{edge.destination}" for edge in graph.edges))
    )
    return WorkflowOrder(identity=hashlib.sha256(topology.encode()).hexdigest()[:16], depth=depth)


def completed_attempt(
    *, run: RecordedRun, payload: object | None, order: WorkflowOrder | None
) -> CompletedAttempt:
    """Classify one run's record into the progress decision's attempt vocabulary."""
    identity = order.identity if order is not None else f"unresolved:{run.run_id}"
    record = fabro_inspect_record(payload=payload)
    kind = fabro_status_kind_from_payload(payload=payload)
    if record is None or kind is None:
        where = run.factory or "no recorded factory"
        return CompletedAttempt(
            run_id=run.run_id,
            terminal_cause=f"run record unreadable from {where}",
            high_water_milestone=_NO_MILESTONE,
            item_attributable=None,
            workflow_identity=identity,
            high_water_order=-1,
        )
    outcomes = _outcomes(record=record)
    milestone, level = _high_water(outcomes=outcomes, order=order)
    failed = tuple(
        stage
        for stage, outcome in outcomes.items()
        if fabro_stage_node(stage=stage) != _ESCALATION_NODE
        and str(outcome.get("status", "")).casefold() == _FAILED_STATUS
    )
    cause, attributable = _cause(kind=kind.casefold(), payload=payload, failed=failed)
    return CompletedAttempt(
        run_id=run.run_id,
        terminal_cause=cause,
        high_water_milestone=milestone,
        item_attributable=attributable,
        workflow_identity=identity,
        high_water_order=level,
        completed=kind.casefold() in _TERMINAL_KINDS,
    )


def _outcomes(*, record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checkpoints = fabro_inspect_checkpoints(record=record)
    return fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})


def _high_water(
    *, outcomes: Mapping[str, Mapping[str, Any]], order: WorkflowOrder | None
) -> tuple[str, int]:
    if order is None:
        return _NO_MILESTONE, -1
    best = (_NO_MILESTONE, -1)
    for stage, outcome in outcomes.items():
        node = fabro_stage_node(stage=stage)
        level = order.depth.get(node)
        status = str(outcome.get("status", "")).casefold()
        if level is not None and status in _SUCCESS_STATUSES and level >= best[1]:
            best = (node, level)
    return best


def _cause(
    *, kind: str, payload: object | None, failed: tuple[str, ...]
) -> tuple[str, bool | None]:
    if kind == "succeeded":
        return "succeeded", True
    if kind in _HOST_KINDS:
        return f"run {kind} outside the item's own stages", False
    detail = fabro_failure_detail_from_payload(payload=payload)
    text = (
        " ".join(part for part in (detail.cause, detail.signature) if part is not None)
        if detail is not None
        else ""
    )
    if detail is not None and detail.provider_usage_limit:
        return _excerpt(stage=None, text=text or "provider usage limit"), False
    if any(marker in text.casefold() for marker in _HOST_MARKERS):
        return _excerpt(stage=None, text=text), False
    if kind == _FAILED_STATUS and failed:
        return _excerpt(stage=failed[-1], text=text or "stage failed"), True
    return _excerpt(stage=None, text=text or f"run {kind} with no recorded cause"), None


def _excerpt(*, stage: str | None, text: str) -> str:
    cause = f"{stage}: {text}" if stage is not None else text
    return cause[:_CAUSE_EXCERPT]
