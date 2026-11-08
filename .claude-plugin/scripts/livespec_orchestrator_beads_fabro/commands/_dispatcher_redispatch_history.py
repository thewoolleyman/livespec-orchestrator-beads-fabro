"""One item's completed dispatch attempts, graded against its recorded factories.

The across-dispatch progress rule needs three facts per run that no single
record holds: which factory the run was submitted to (the `dispatch-run-stamp`
row), what the Dispatcher saw end (the `outcome` row), and how far the run got
(that factory's own record of it).  A run's evidence is read from the factory
the stamp names and from no other: an unconfigured or unreachable factory leaves
the cause unknown, which the rule turns into a diagnosis, rather than a local
default server standing in for remote history.

Progress is the position of the furthest successful node in the workflow
graph's own dependency order (shortest distance from the start node), never a
stage name or a retry number.  The graph a run executed is identified by a digest
of its nodes and edges, so a changed graph is an incomparable variant.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import (
    START_SHAPE,
    WorkflowGraph,
    parse_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_graph import (
    workflow_graph_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import RELEASE_STAGES
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
    fabro_status_kind_from_payload,
)

__all__: list[str] = [
    "RecordedRun",
    "RunPayloadReader",
    "attempts_from_runs",
    "recorded_runs",
    "with_diagnosed",
]

RunPayloadReader = Callable[[str, str], object | None]

_GREEN_STATUS = "green"
_HOST_STATUSES = frozenset({"cancelled", "stalled-no-progress", "run-unobservable"})
_HOST_STAGES = frozenset({*RELEASE_STAGES, STALL_CANCEL_STAGE})
_ACTIVE_RUN_STATUSES = frozenset(
    {"running", "runnable", "submitted", "queued", "starting", "paused", "pending"}
)
_SUCCEEDED = "succeeded"
_FAILED = "failed"
_CAUSE_LIMIT = 160
_UNREADABLE_WORKFLOW = "unreadable-workflow"
_NO_MILESTONE = "no milestone reached"


@dataclass(frozen=True, kw_only=True)
class RecordedRun:
    """One terminal the Dispatcher journaled for the item, with what it recorded."""

    run_id: str
    factory: str | None
    status: str
    detail: str
    host_attributable: bool
    workflow_toml: str | None


@dataclass(frozen=True, kw_only=True)
class _Workflow:
    identity: str
    order: Mapping[str, int]
    terminals: frozenset[str]


@dataclass(kw_only=True)
class _Journal:
    """What one pass over the journal collects for a single item."""

    workflow_by_dispatch: dict[str, str] = field(default_factory=dict)
    stamps: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    host_runs: set[str] = field(default_factory=set)
    terminals: list[Mapping[str, object]] = field(default_factory=list)


def recorded_runs(
    *, records: Sequence[Mapping[str, object]], item_id: str
) -> tuple[RecordedRun, ...]:
    """The item's journaled terminals in append order, each joined to its stamp."""
    journal = _Journal()
    for record in records:
        _note(journal=journal, record=record, item_id=item_id)
    runs: list[RecordedRun] = []
    for terminal in journal.terminals:
        run_id = terminal.get("fabro_run_id")
        if terminal.get("work_item_id") == item_id and isinstance(run_id, str):
            runs.append(_recorded(journal=journal, terminal=terminal, run_id=run_id))
    return tuple(runs)


def _note(*, journal: _Journal, record: Mapping[str, object], item_id: str) -> None:
    stage = record.get("stage")
    if stage == "outcome":
        outcome = record.get("outcome")
        if isinstance(outcome, dict):
            journal.terminals.append(cast("Mapping[str, object]", outcome))
        return
    if record.get("work_item_id") != item_id:
        return
    dispatch = record.get("dispatch_id")
    run = record.get("run_id")
    if stage == "dispatch-id" and isinstance(dispatch, str):
        _bind(table=journal.workflow_by_dispatch, key=dispatch, value=record.get("workflow_toml"))
    elif stage == "dispatch-run-stamp" and isinstance(run, str):
        journal.stamps[run] = (_text(value=record.get("dispatch_factory")), _text(value=dispatch))
    elif stage in _HOST_STAGES and isinstance(run, str):
        journal.host_runs.add(run)


def _recorded(*, journal: _Journal, terminal: Mapping[str, object], run_id: str) -> RecordedRun:
    factory, dispatch_id = journal.stamps.get(run_id, (None, None))
    status = _text(value=terminal.get("status")) or ""
    return RecordedRun(
        run_id=run_id,
        factory=factory,
        status=status,
        detail=_text(value=terminal.get("detail")) or "",
        host_attributable=run_id in journal.host_runs
        or status in _HOST_STATUSES
        or terminal.get("provider_usage_limit") is True,
        workflow_toml=journal.workflow_by_dispatch.get(dispatch_id or ""),
    )


def attempts_from_runs(
    *, runs: Sequence[RecordedRun], run_payload: RunPayloadReader
) -> tuple[CompletedAttempt, ...]:
    """Grade each recorded run into the attempt the progress rule compares."""
    workflows: dict[str, _Workflow | None] = {}
    attempts: list[CompletedAttempt] = []
    for run in runs:
        key = run.workflow_toml or ""
        if key not in workflows:
            workflows[key] = _workflow(workflow_toml=run.workflow_toml)
        attempts.append(_attempt(run=run, workflow=workflows[key], run_payload=run_payload))
    return tuple(attempts)


def _attempt(
    *, run: RecordedRun, workflow: _Workflow | None, run_payload: RunPayloadReader
) -> CompletedAttempt:
    identity = f"{_UNREADABLE_WORKFLOW}:{run.run_id}" if workflow is None else workflow.identity
    cause = (run.detail.splitlines() or [run.status])[0][:_CAUSE_LIMIT] or run.status
    if run.status == _GREEN_STATUS:
        top = 0 if workflow is None else len(workflow.order)
        return CompletedAttempt(
            run_id=run.run_id,
            terminal_cause=cause,
            high_water_milestone="green",
            high_water_order=top,
            item_attributable=True,
            workflow_identity=identity,
        )
    payload = None if run.factory is None else run_payload(run.factory, run.run_id)
    milestone, order = _high_water(payload=payload, workflow=workflow)
    active = (
        run.status == "run-unobservable"
        or fabro_status_kind_from_payload(payload=payload) in _ACTIVE_RUN_STATUSES
    )
    return CompletedAttempt(
        run_id=run.run_id,
        terminal_cause=cause,
        high_water_milestone=milestone,
        high_water_order=order,
        item_attributable=_attributable(run=run, payload=payload, workflow=workflow),
        workflow_identity=identity,
        completed=not active,
    )


def _attributable(
    *, run: RecordedRun, payload: object | None, workflow: _Workflow | None
) -> bool | None:
    """Item-attributable, known host-attributable, or unknown (`None`)."""
    if run.host_attributable:
        return False
    if NON_CONVERGED_MARKER in run.detail:
        return True
    if payload is None or workflow is None:
        return None
    outcomes = _outcomes(payload=payload)
    failed = [node for node, status in outcomes.items() if status == _FAILED]
    if any(node in workflow.order and node not in workflow.terminals for node in failed):
        return True
    return None


def _high_water(*, payload: object | None, workflow: _Workflow | None) -> tuple[str, int]:
    if payload is None or workflow is None:
        return _NO_MILESTONE, -1
    reached = [
        node
        for node, status in _outcomes(payload=payload).items()
        if status == _SUCCEEDED and node in workflow.order
    ]
    if not reached:
        return _NO_MILESTONE, -1
    furthest = max(reached, key=lambda node: workflow.order[node])
    return furthest, workflow.order[furthest]


def _outcomes(*, payload: object) -> dict[str, str]:
    """Node → latest status from one run record, visit suffixes divided off."""
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return {}
    checkpoints = fabro_inspect_checkpoints(record=record)
    graded = fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})
    statuses: dict[str, str] = {}
    for stage, outcome in graded.items():
        status = outcome.get("status")
        if isinstance(status, str):
            statuses[fabro_stage_node(stage=stage)] = status
    return statuses


def _workflow(*, workflow_toml: str | None) -> _Workflow | None:
    if workflow_toml is None:
        return None
    manifest = Path(workflow_toml)
    try:
        graph_path = workflow_graph_path(
            committed_text=manifest.read_text(encoding="utf-8"),
            workflow_dir=manifest.parent.resolve(),
        )
        graph_text = None if graph_path is None else graph_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if graph_text is None:
        return None
    return _graph_workflow(graph=parse_workflow_graph(text=graph_text))


def _graph_workflow(*, graph: WorkflowGraph) -> _Workflow | None:
    starts = graph.with_shape(shape=START_SHAPE)
    if not starts:
        return None
    order = {starts[0]: 0}
    queue = deque([starts[0]])
    while queue:
        node = queue.popleft()
        for successor in graph.successors(node=node):
            if successor not in order:
                order[successor] = order[node] + 1
                queue.append(successor)
    shape = "|".join((*graph.names, *(f"{source}>{target}" for source, target in graph.edges)))
    return _Workflow(
        identity=hashlib.sha256(shape.encode("utf-8")).hexdigest()[:16],
        order=order,
        terminals=frozenset(name for name in graph.names if not graph.successors(node=name)),
    )


def _bind(*, table: dict[str, str], key: object, value: object) -> None:
    if isinstance(key, str) and isinstance(value, str):
        table[key] = value


def _text(*, value: object) -> str | None:
    return value if isinstance(value, str) else None


def with_diagnosed(
    *, attempts: Sequence[CompletedAttempt], run_ids: frozenset[str]
) -> tuple[CompletedAttempt, ...]:
    """Mark the attempts a consumed diagnosis recovery already covered."""
    return tuple(
        replace(attempt, diagnosed=True) if attempt.run_id in run_ids else attempt
        for attempt in attempts
    )
