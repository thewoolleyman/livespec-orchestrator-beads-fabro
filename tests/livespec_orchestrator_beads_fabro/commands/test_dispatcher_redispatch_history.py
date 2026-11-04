"""Run records classify into progress attempts by dependency order, not by name."""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_history import (
    RecordedRun,
    WorkflowOrder,
    completed_attempt,
    recorded_runs,
    workflow_order,
)

_GRAPH = (
    "digraph G { start [shape=Mdiamond]; start -> build; build -> check; check -> ship; "
    "check -> build; }"
)
_ORDER = WorkflowOrder(identity="x", depth={"start": 0, "build": 1, "check": 2, "ship": 3})
_RUN = RecordedRun(run_id="R1", factory="petri", workflow_name=None)


def _payload(
    *, kind: str | None, outcomes: Mapping[str, object] | None = None, key: str = "checkpoint"
) -> object:
    record: dict[str, object] = {}
    if kind is not None:
        record["status"] = {"kind": kind}
    if outcomes is not None:
        record[key] = {"node_outcomes": outcomes} if key == "checkpoint" else outcomes
    return [record]


def _failure(*, cause: str) -> dict[str, object]:
    return {"status": "failed", "failure": {"category": "deterministic", "causes": [cause]}}


def test_recorded_runs_keep_the_stamped_factory_and_join_the_workflow() -> None:
    """One run per id, in order, for the named item only, joined by dispatch id."""
    records = [
        {"stage": "dispatch-id", "dispatch_id": "D1", "workflow_name": "custom"},
        {"stage": "dispatch-id", "dispatch_id": 7, "workflow_name": "ignored"},
        {"stage": "dispatch-run-stamp", "work_item_id": "i", "run_id": "A", "dispatch_id": "D1"},
        {
            "stage": "dispatch-run-stamp",
            "work_item_id": "i",
            "run_id": "A",
            "dispatch_factory": "x",
        },
        {
            "stage": "dispatch-run-stamp",
            "work_item_id": "i",
            "run_id": "B",
            "dispatch_factory": "hp",
        },
        {"stage": "dispatch-run-stamp", "work_item_id": "other", "run_id": "C"},
        {"stage": "dispatch-run-stamp", "work_item_id": "i", "run_id": 5},
        {"stage": "outcome", "work_item_id": "i", "run_id": "D"},
    ]
    runs = recorded_runs(records=records, work_item_id="i")
    assert [(run.run_id, run.factory, run.workflow_name) for run in runs] == [
        ("A", None, "custom"),
        ("B", "hp", None),
    ]


def test_workflow_order_is_dependency_depth_and_topology_identity() -> None:
    """A back edge does not change depth, and attributes do not change identity."""
    order = workflow_order(graph_text=_GRAPH)
    assert order is not None
    assert order.depth == {"start": 0, "build": 1, "check": 2, "ship": 3}
    renamed_attribute = workflow_order(graph_text=_GRAPH.replace("shape=Mdiamond", "shape=box"))
    assert renamed_attribute is not None
    assert renamed_attribute.identity == order.identity
    other = workflow_order(graph_text=_GRAPH.replace("check -> ship", "check -> done"))
    assert other is not None
    assert other.identity != order.identity
    assert workflow_order(graph_text=None) is None
    assert workflow_order(graph_text="not a graph") is None


def test_a_failed_item_stage_is_attributable_and_marks_the_deepest_success() -> None:
    """The high-water mark is the deepest succeeded node, escalation excluded."""
    outcomes: dict[str, object] = {
        "start": {"status": "succeeded"},
        "build@2": {"status": "succeeded"},
        "check": _failure(cause="check refused"),
        "mystery": {"status": "succeeded"},
        "needs_human": {"status": "failed"},
    }
    attempt = completed_attempt(
        run=_RUN, payload=_payload(kind="failed", outcomes=outcomes), order=_ORDER
    )
    assert attempt.item_attributable is True
    assert attempt.high_water_milestone == "build"
    assert attempt.high_water_order == 1
    assert attempt.terminal_cause.startswith("check: ")
    assert "check refused" in attempt.terminal_cause
    assert attempt.completed is True


def test_a_succeeded_run_reaches_its_deepest_milestone() -> None:
    """A normal success is attributable and advances past every failure."""
    outcomes: dict[str, object] = {
        name: {"status": "succeeded"} for name in ("build", "check", "ship")
    }
    attempt = completed_attempt(
        run=_RUN, payload=_payload(kind="succeeded", outcomes=outcomes), order=_ORDER
    )
    assert (attempt.terminal_cause, attempt.item_attributable) == ("succeeded", True)
    assert (attempt.high_water_milestone, attempt.high_water_order) == ("ship", 3)


def test_host_faults_are_not_attributed_to_the_item() -> None:
    """Cancelled runs, sandbox loss, lock contention and provider limits are host causes."""
    cancelled = completed_attempt(run=_RUN, payload=_payload(kind="canceled"), order=_ORDER)
    assert cancelled.item_attributable is False
    for cause in ("the sandbox became unreachable", "database is locked"):
        outcomes = {"build": _failure(cause=cause)}
        host = completed_attempt(
            run=_RUN, payload=_payload(kind="failed", outcomes=outcomes), order=_ORDER
        )
        assert host.item_attributable is False
    limited = {"build": _failure(cause="You've hit your usage limit for this plan")}
    attempt = completed_attempt(
        run=_RUN, payload=_payload(kind="failed", outcomes=limited), order=_ORDER
    )
    assert attempt.item_attributable is False


def test_unreadable_unknown_and_active_runs_are_not_counted_as_failures() -> None:
    """Silence is an unknown cause; a non-terminal run is not a completed attempt."""
    unreadable = completed_attempt(run=_RUN, payload=None, order=_ORDER)
    assert unreadable.item_attributable is None
    assert "petri" in unreadable.terminal_cause
    unrecorded = completed_attempt(
        run=RecordedRun(run_id="R2", factory=None, workflow_name=None), payload=None, order=_ORDER
    )
    assert "no recorded factory" in unrecorded.terminal_cause
    no_status = completed_attempt(run=_RUN, payload=_payload(kind=None), order=_ORDER)
    assert no_status.item_attributable is None
    bare = completed_attempt(run=_RUN, payload=_payload(kind="failed"), order=_ORDER)
    assert bare.item_attributable is None
    active = completed_attempt(run=_RUN, payload=_payload(kind="running"), order=_ORDER)
    assert active.completed is False


def test_an_unresolved_graph_is_its_own_incomparable_workflow() -> None:
    """Without a graph no milestone can be ordered, and no two runs compare."""
    outcomes = {"build": {"status": "succeeded"}}
    attempt = completed_attempt(
        run=_RUN, payload=_payload(kind="failed", outcomes=outcomes), order=None
    )
    assert attempt.workflow_identity == "unresolved:R1"
    assert (attempt.high_water_milestone, attempt.high_water_order) == ("(none)", -1)


def test_petri_stage_maps_are_read_when_no_checkpoint_is_present() -> None:
    """The Petri record carries `stages` instead of a checkpoint."""
    stages = {"build@1": {"state": "succeeded"}, "check@1": {"state": "failed"}}
    payload = _payload(kind="failed", outcomes=stages, key="stages")
    attempt = completed_attempt(run=_RUN, payload=payload, order=_ORDER)
    assert attempt.high_water_milestone == "build"
    assert attempt.item_attributable is True
