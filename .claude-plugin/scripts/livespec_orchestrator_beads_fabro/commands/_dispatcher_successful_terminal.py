"""Structured checkpoint evidence for a successful route behind run-store loss."""

from __future__ import annotations

from dataclasses import dataclass
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_worker_exit_log_cause import (
    WORKER_EXIT_BEFORE_TERMINAL_EVENT,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "SuccessfulTerminalEvidence",
    "successful_store_loss_evidence",
]

# The engine sentence BOTH readers of this conclusion key on. Named by the
# failure-path sibling and imported rather than copied: two spellings of one
# measured literal are two readings that can drift, and a drifted copy reports
# the ordinary non-green for exactly the runs each rule exists to read.
_RUN_STORE_LOSS_MESSAGE = WORKER_EXIT_BEFORE_TERMINAL_EVENT


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
    # ONE reading of the engine's grading, shared with `_fabro_terminal_evidence`
    # through the port rather than re-derived: that reader already resolves BOTH
    # inputs the two engines write -- the checkpoint's `node_outcomes`, else the
    # record's own top-level `stages` map, visit-collapsed -- and a second
    # reading here would make the two disagree about whether one record is
    # readable at all, which is the answer that keeps a merged pull request
    # classified as a failed dispatch.
    outcomes = {} if record is None else fabro_node_outcomes(record=record, checkpoint=checkpoint)
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
    configured = _configured_success_route(plan=plan)
    if configured is None:
        return None
    graph, route = configured
    if not _checkpoint_completed_route(
        checkpoint=checkpoint, outcomes=outcomes, graph=graph, route=route
    ):
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


def _configured_success_route(
    *, plan: DispatchPlan
) -> tuple[WorkflowGraph, SuccessCriticalNodes] | None:
    """Read the green terminal from the exact graph configured for this run.

    EVERY arm that cannot MEASURE that terminal yields no evidence rather than
    raising, which is the same rule `_node_succeeded` states one level down and
    for the same reason: a route nobody could read is unavailable evidence, and
    letting it escape turned an unreadable workflow into a traceback out of the
    middle of `run_dispatch` -- abandoning the dispatch and leaving the ledger
    claim dangling instead of keeping the ordinary non-green outcome. Four
    conditions reach it, each measured against this tree: a run config that
    cannot be read, one declaring no `[workflow] graph`, a declared graph file
    that is not there, and a graph whose shape `derive_success_critical`
    refuses. The two refusals are DOCUMENTED return arms -- `Path | None` and
    `SuccessCriticalNodes | str` -- so they are branched on here as every peer
    reader in this package already branches on them, never cast away.
    """
    manifest = attempt(
        action=lambda: plan.workflow_toml.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(manifest, AttemptFailure):
        return None
    graph_path = workflow_graph_path(
        committed_text=manifest,
        workflow_dir=plan.workflow_toml.parent.resolve(),
    )
    if graph_path is None:
        return None
    graph_text = attempt(
        action=lambda: graph_path.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(graph_text, AttemptFailure):
        return None
    graph = parse_workflow_graph(text=graph_text)
    route = derive_success_critical(graph=graph)
    if isinstance(route, str):
        return None
    return graph, route


def _checkpoint_completed_route(
    *,
    checkpoint: dict[str, Any],
    outcomes: dict[str, dict[str, Any]],
    graph: WorkflowGraph,
    route: SuccessCriticalNodes,
) -> bool:
    """Whether the newest checkpoint proves either supported green-terminal shape.

    BOTH shapes the engine uses are accepted and neither is sufficient alone:
    a checkpoint AT the green terminal, and a checkpoint at the final
    successful stage whose next node IS that terminal. The incident's own
    record is the second shape, so requiring a completed exit-node entry would
    refuse the very evidence this rule exists to read.

    THE TWO QUESTIONS ASKED OF THE DOMINATING STAGES ARE SEPARATE, and conflating
    them refused every real record. COMPLETION is asked of all of them, against
    `completed_nodes`, which is the engine's own account of what it ran and is
    what keeps an intermediate checkpoint out. SUCCESS is asked only of the ones
    the engine ACTUALLY GRADED, because the outcome map is not complete over that
    list: both committed `fabro inspect --json` captures name `dod_gate` in
    `completed_nodes` with no outcome entry at all, and the graph's own entry
    marker -- `start [shape=Mdiamond]`, no backend, no script -- has never had
    anything for any engine to grade. Demanding a `succeeded` entry per dominator
    therefore reported NO evidence for the shape this rule exists to read, which
    is indistinguishable at every surface from the correct fail-closed answer. A
    dominator the engine never graded is UNGRADED, never failed; one it graded as
    anything but succeeded still refuses, which is what keeps a genuinely failed
    required stage out.

    THE ENTRY MARKER IS RELIEVED OF THE COMPLETION AS WELL AS OF THE GRADE, and
    the earlier asymmetry here was a measured defect rather than a conservative
    choice. That reading held that `completed_nodes` is the engine's own account
    of the nodes it ran and that nothing said any engine omits the marker from
    it. Both committed `fabro inspect --json` captures say exactly that: each
    opens with `setup` -- the engine's own name for the marker -- and NEITHER
    names `start`, and no revision of the graph has ever declared a `setup` node.
    Nothing executes at `start [shape=Mdiamond]`, which declares no backend and
    no script, so the engine's account of what it RAN cannot contain it.

    Requiring it therefore refused 100% of real records while reporting the same
    clean non-green a genuine failure reports -- indistinguishable at every
    surface from the correct fail-closed answer, which is the one way this rule
    can fail without anyone noticing. Nothing is given up by relieving it: the
    marker dominates every node in the graph, so it carries no discriminating
    information, and the route still rests on every EXECUTABLE dominator
    completing and on the terminal-shape test below. The GRADE still ranges over
    the whole dominating set, so an engine that did grade the marker and graded
    it anything but succeeded still refuses.

    The `outcomes` map arrives ALREADY RESOLVED from the port, keyed as the
    engine wrote it, so a Petri `<node>@<visit>` key is divided here through
    that port's own reading rather than compared whole against a node id.
    """
    completed_raw: object = checkpoint.get("completed_nodes")
    current_raw: object = checkpoint.get("current_node")
    # FAIL CLOSED on a checkpoint whose own shape cannot be read, and on a record
    # that graded NOTHING. Either is a failure to MEASURE the route, not a route
    # that was measured and found complete -- and the natural coding of "no
    # missing stage found" is a pass earned on data nobody could read.
    if not isinstance(completed_raw, list) or not isinstance(current_raw, str) or not outcomes:
        return False
    completed = frozenset(
        item for item in cast("list[object]", completed_raw) if isinstance(item, str)
    )
    states = {fabro_stage_node(stage=stage): outcome for stage, outcome in outcomes.items()}
    successful = frozenset(node for node in states if _node_succeeded(states=states, node=node))
    required = dominators(graph=graph, start=route.start)[route.green_terminal]
    preceding = required - {route.green_terminal}
    # `dominators` always reports the start in its own dominator set, so the
    # entry marker is in EVERY graph's `preceding`. COMPLETION is asked only of
    # the dominators an engine can actually run; the GRADE still ranges over all
    # of them.
    executed = preceding - {route.start}
    route_completed = executed.issubset(completed) and (preceding & frozenset(states)).issubset(
        successful
    )
    terminal_completed = (
        current_raw == route.green_terminal
        and route.green_terminal in completed
        and route.green_terminal in successful
    )
    final_stage_selected_terminal = (
        checkpoint.get("next_node_id") == route.green_terminal
        and current_raw in graph.predecessors(node=route.green_terminal)
        and current_raw in successful
    )
    return route_completed and (terminal_completed or final_stage_selected_terminal)


def _node_succeeded(*, states: dict[str, dict[str, Any]], node: str) -> bool:
    """Treat an ABSENT or ungradeable outcome as not succeeded, never as a bug.

    A node with no recorded outcome, or one the port could not read, is evidence
    that could not be read -- so it fails this test, and a node the ROUTE requires
    is then judged on completion alone rather than refused for an entry no engine
    writes. Indexing an unreadable entry as a mapping raised instead, which turned
    unreadable engine evidence into a traceback out of the middle of
    `run_dispatch`.
    """
    outcome = states.get(node)
    return outcome is not None and outcome.get("status") == "succeeded"
