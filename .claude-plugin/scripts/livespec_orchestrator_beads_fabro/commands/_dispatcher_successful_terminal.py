"""Structured checkpoint evidence for a successful route behind run-store loss."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_success_critical import (
    SuccessCriticalNodes,
    derive_success_critical,
    dominators,
)
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import (
    WorkflowGraph,
    parse_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "SuccessfulTerminalEvidence",
    "successful_store_loss_evidence",
]

_RUN_STORE_LOSS_MESSAGE = "Worker exited before emitting a terminal run event: exit status: 0"


@dataclass(frozen=True, kw_only=True)
class SuccessfulTerminalEvidence:
    """The current run's checkpoint and its contradictory engine conclusion.

    BOTH SIDES OF THE CONFLICT travel together, because the journal has to
    record them SEPARATELY: the checkpoint fields are what establishes the
    successful workflow, and the engine fields are the conclusion that
    contradicts it. A value carrying only the verdict would leave the
    conflicting evidence recoverable from nowhere but the run export, which is
    pruned long before anyone asks why a dispatch was classified this way.
    """

    run_id: str
    timestamp: str
    current_node: str
    next_node_id: str | None
    commit_sha: str
    engine_status: str
    failure_cause: str
    failure_category: str | None


def successful_store_loss_evidence(
    *,
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
) -> SuccessfulTerminalEvidence | None:
    """Return the incident's structured evidence, or no override.

    The STRUCTURED EVIDENCE is what the caller needs rather than a bare
    verdict or a lone head: the checkpoint's own `git_commit_sha` is the commit
    the successful run published, so it is the only value a publication can be
    authenticated against, and the timestamp and node pair beside it are what a
    reader needs to see which checkpoint was believed. A qualifying checkpoint
    missing any of them is therefore no evidence at all.

    The engine's own conclusion says the worker exited before persisting a
    terminal run event, so it cannot answer whether the workflow completed.
    The newest STRUCTURED checkpoint for THIS run can: it names the stage the
    run reached, the node it selected next, and that stage's own outcome. A
    checkpoint belonging to another run, a conclusion whose cause is anything
    but the run-store loss, and an inspection that could not be taken are all
    read as no evidence rather than as success.

    THE GREEN TERMINAL IS DERIVED FROM THE GRAPH THIS RUN WAS CONFIGURED WITH,
    never from a node name spelled here. A spelled pair recognises exactly one
    graph: it refused the engine's OTHER representation of the same success (a
    completed exit node) and it would silently stop recognising anything at all
    if the graph's final stage were renamed, while still reporting a confident
    non-green.
    """
    record = None if inspect is None else fabro_inspect_record(payload=inspect.payload)
    checkpoints = () if record is None else fabro_inspect_checkpoints(record=record)
    checkpoint: dict[str, Any] = {} if not checkpoints else checkpoints[-1]
    failure = None if inspect is None else inspect.failure
    timestamp_raw: object = checkpoint.get("timestamp")
    commit_raw: object = checkpoint.get("git_commit_sha")
    conflict_qualifies = bool(
        run_id is not None
        and inspect is not None
        and inspect.command.exit_code == 0
        and inspect.status_kind == "failed"
        and failure is not None
        and failure.cause == _RUN_STORE_LOSS_MESSAGE
        and record is not None
        and record.get("run_id") == run_id
        and isinstance(timestamp_raw, str)
        and isinstance(commit_raw, str)
    )
    if not conflict_qualifies or failure is None:
        return None
    graph, route = _configured_success_route(plan=plan)
    if not _checkpoint_completed_route(checkpoint=checkpoint, graph=graph, route=route):
        return None
    current_node = cast("str", checkpoint.get("current_node"))
    next_node_raw: object = checkpoint.get("next_node_id")
    return SuccessfulTerminalEvidence(
        run_id=cast("str", run_id),
        timestamp=cast("str", timestamp_raw),
        current_node=current_node,
        next_node_id=next_node_raw if isinstance(next_node_raw, str) else None,
        commit_sha=cast("str", commit_raw),
        engine_status="failed",
        failure_cause=cast("str", failure.cause),
        failure_category=failure.category,
    )


def _configured_success_route(*, plan: DispatchPlan) -> tuple[WorkflowGraph, SuccessCriticalNodes]:
    """Read the green terminal from the exact graph configured for this run."""
    manifest = plan.workflow_toml.read_text(encoding="utf-8")
    graph_path = cast(
        "Path",
        workflow_graph_path(
            committed_text=manifest,
            workflow_dir=plan.workflow_toml.parent.resolve(),
        ),
    )
    graph = parse_workflow_graph(text=graph_path.read_text(encoding="utf-8"))
    return graph, cast("SuccessCriticalNodes", derive_success_critical(graph=graph))


def _checkpoint_completed_route(
    *,
    checkpoint: dict[str, Any],
    graph: WorkflowGraph,
    route: SuccessCriticalNodes,
) -> bool:
    """Whether the newest checkpoint proves either supported green-terminal shape.

    BOTH shapes the engine uses are accepted and neither is sufficient alone:
    a checkpoint AT the green terminal, and a checkpoint at the final
    successful stage whose next node IS that terminal. The incident's own
    record is the second shape, so requiring a completed exit-node entry would
    refuse the very evidence this rule exists to read. Either way every stage
    DOMINATING the terminal must also be completed AND successful, which is
    what keeps an intermediate checkpoint and a failed required stage out.
    """
    completed_raw: object = checkpoint.get("completed_nodes")
    outcomes_raw: object = checkpoint.get("node_outcomes")
    current_raw: object = checkpoint.get("current_node")
    # FAIL CLOSED on a checkpoint whose own shape cannot be read. An unreadable
    # node list or outcome map is a failure to MEASURE the route, not a route
    # that was measured and found complete -- and the natural coding of "no
    # missing stage found" is a pass earned on data nobody could read.
    if (
        not isinstance(completed_raw, list)
        or not isinstance(outcomes_raw, dict)
        or not isinstance(current_raw, str)
    ):
        return False
    completed = frozenset(
        item for item in cast("list[object]", completed_raw) if isinstance(item, str)
    )
    outcomes = cast("dict[object, object]", outcomes_raw)
    required = dominators(graph=graph, start=route.start)[route.green_terminal]
    preceding = required - {route.green_terminal}
    successful = frozenset(
        cast("str", node)
        for node in outcomes
        if _node_succeeded(outcomes=outcomes, node=cast("str", node))
    )
    required_completed = preceding.issubset(completed & successful)
    terminal_completed = (
        current_raw == route.green_terminal
        and route.green_terminal in completed
        and _node_succeeded(outcomes=outcomes, node=route.green_terminal)
    )
    final_stage_selected_terminal = (
        checkpoint.get("next_node_id") == route.green_terminal
        and current_raw in graph.predecessors(node=route.green_terminal)
        and _node_succeeded(outcomes=outcomes, node=current_raw)
    )
    return required_completed and (terminal_completed or final_stage_selected_terminal)


def _node_succeeded(*, outcomes: dict[object, object], node: str) -> bool:
    raw = cast("dict[object, object]", outcomes.get(node))
    return raw.get("status") == "succeeded"
