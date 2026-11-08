"""Journal rows become graded attempts from each run's recorded factory."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_history import (
    RecordedRun,
    attempts_from_runs,
    recorded_runs,
    with_diagnosed,
)

_GRAPH = """digraph g {
  start [shape=Mdiamond]
  implement [shape=box]
  review [shape=box]
  pr [shape=box]
  exit [shape=Msquare]
  needs_human [shape=parallelogram]
  start -> implement
  implement -> review
  review -> pr
  pr -> exit
  review -> needs_human
  review -> implement
}
"""
_ITEM = "bd-x"


def _workflow(root: Path, *, graph: str | None = _GRAPH, key: bool = True) -> str:
    manifest = root / "workflow.toml"
    _ = manifest.write_text(
        '[workflow]\ngraph = "graph.dot"\n' if key else "[run]\n", encoding="utf-8"
    )
    if graph is not None:
        _ = (root / "graph.dot").write_text(graph, encoding="utf-8")
    return str(manifest)


def _run(
    run_id: str,
    *,
    workflow: str | None,
    status: str = "blocked",
    detail: str = "review failed",
    factory: str | None = "petri",
    host: bool = False,
) -> RecordedRun:
    return RecordedRun(
        run_id=run_id,
        factory=factory,
        status=status,
        detail=detail,
        host_attributable=host,
        workflow_toml=workflow,
    )


def _payload(*, done: tuple[str, ...], failed: tuple[str, ...], status: str = "failed") -> object:
    outcomes = {node: {"status": "succeeded"} for node in done}
    outcomes.update({node: {"status": "failed"} for node in failed})
    return [{"status": status, "checkpoint": {"node_outcomes": outcomes}}]


def test_recorded_runs_join_stamp_workflow_and_host_evidence() -> None:
    """Each terminal carries its stamped factory, its dispatch's workflow and host marks."""
    records: list[dict[str, object]] = [
        {"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": "d1", "workflow_toml": "/w"},
        {
            "stage": "dispatch-id",
            "work_item_id": "other",
            "dispatch_id": "d9",
            "workflow_toml": "/x",
        },
        {"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": "d2"},
        {
            "stage": "dispatch-run-stamp",
            "work_item_id": _ITEM,
            "run_id": "r1",
            "dispatch_id": "d1",
            "dispatch_factory": "petri",
        },
        {"stage": "dispatch-run-stamp", "work_item_id": _ITEM, "dispatch_id": "d1"},
        {"stage": "provider-limit-release", "work_item_id": _ITEM, "run_id": "r2"},
        {"stage": "provider-limit-release", "work_item_id": _ITEM},
        {"stage": "watchdog-stall-cancel", "work_item_id": "other", "run_id": "r1"},
        {
            "stage": "outcome",
            "outcome": {
                "work_item_id": _ITEM,
                "status": "blocked",
                "fabro_run_id": "r1",
                "detail": "bad",
            },
        },
        {
            "stage": "outcome",
            "outcome": {"work_item_id": _ITEM, "status": "failed", "fabro_run_id": "r2"},
        },
        {
            "stage": "outcome",
            "outcome": {"work_item_id": _ITEM, "status": "cancelled", "fabro_run_id": "r3"},
        },
        {
            "stage": "outcome",
            "outcome": {
                "work_item_id": _ITEM,
                "status": "failed",
                "fabro_run_id": "r4",
                "provider_usage_limit": True,
            },
        },
        {
            "stage": "outcome",
            "outcome": {"work_item_id": "other", "status": "failed", "fabro_run_id": "r5"},
        },
        {"stage": "outcome", "outcome": {"work_item_id": _ITEM, "status": "failed"}},
        {"stage": "outcome", "outcome": "not a mapping"},
        {"stage": "outcome", "outcome": {"work_item_id": _ITEM, "fabro_run_id": "r6"}},
    ]
    runs = recorded_runs(records=records, item_id=_ITEM)
    assert [run.run_id for run in runs] == ["r1", "r2", "r3", "r4", "r6"]
    assert (runs[0].factory, runs[0].workflow_toml, runs[0].detail) == ("petri", "/w", "bad")
    assert [run.host_attributable for run in runs] == [False, True, True, True, False]
    assert (runs[4].status, runs[4].factory, runs[4].workflow_toml) == ("", None, None)


def test_progress_is_read_from_graph_order_on_the_recorded_factory(tmp_path: Path) -> None:
    """Furthest successful node by graph distance, read from the stamped factory."""
    workflow = _workflow(tmp_path)
    asked: list[tuple[str, str]] = []

    def reader(factory: str, run_id: str) -> object | None:
        asked.append((factory, run_id))
        return _payload(done=("implement", "review", "unknown-node"), failed=("pr",))

    (attempt,) = attempts_from_runs(runs=[_run("r1", workflow=workflow)], run_payload=reader)
    assert asked == [("petri", "r1")]
    assert (attempt.high_water_milestone, attempt.high_water_order) == ("review", 2)
    assert attempt.item_attributable is True
    assert attempt.completed is True


def test_a_failed_terminal_node_or_empty_record_is_not_a_stage_failure(tmp_path: Path) -> None:
    """Only a failed non-terminal node of the graph attributes the failure to the item."""
    workflow = _workflow(tmp_path)

    def terminal_only(_factory: str, _run: str) -> object | None:
        return _payload(done=("implement",), failed=("needs_human", "stranger"))

    def nothing_reached(_factory: str, _run: str) -> object | None:
        return _payload(done=(), failed=("implement",))

    only_terminal, nothing = (
        attempts_from_runs(runs=[_run("r", workflow=workflow)], run_payload=reader)[0]
        for reader in (terminal_only, nothing_reached)
    )
    assert only_terminal.item_attributable is None
    assert (nothing.high_water_milestone, nothing.high_water_order) == ("no milestone reached", -1)
    assert nothing.item_attributable is True


def test_non_convergence_is_the_items_and_host_marks_are_not(tmp_path: Path) -> None:
    """The non-converged sentinel attributes to the item; a host mark never does."""
    workflow = _workflow(tmp_path)

    def unreadable(_factory: str, _run: str) -> object | None:
        return None

    marker = _run("r1", workflow=workflow, detail="LIVESPEC_NON_CONVERGED after the cap")
    host = _run("r2", workflow=workflow, host=True)
    first, second = attempts_from_runs(runs=[marker, host], run_payload=unreadable)
    assert first.item_attributable is True
    assert second.item_attributable is False


def test_unreadable_evidence_and_workflows_leave_the_cause_unknown(tmp_path: Path) -> None:
    """No factory, no payload and no graph each answer unknown, never a guess."""
    workflow = _workflow(tmp_path)
    calls: list[str] = []

    def reader(_factory: str, run_id: str) -> object | None:
        calls.append(run_id)
        return None

    no_factory = _run("r1", workflow=workflow, factory=None)
    no_payload = _run("r2", workflow=workflow)
    no_workflow = _run("r3", workflow=None)
    attempts = attempts_from_runs(runs=[no_factory, no_payload, no_workflow], run_payload=reader)
    assert [attempt.item_attributable for attempt in attempts] == [None, None, None]
    assert calls == ["r2", "r3"]
    assert attempts[2].workflow_identity == "unreadable-workflow:r3"
    assert attempts[0].workflow_identity == attempts[1].workflow_identity


def test_each_unusable_workflow_file_is_an_unreadable_workflow(tmp_path: Path) -> None:
    """A missing manifest, graph key, graph file or start node is unreadable."""

    def reader(_factory: str, _run: str) -> object | None:
        return None

    gone = str(tmp_path / "missing.toml")
    keyless_root = tmp_path / "a"
    keyless_root.mkdir()
    keyless = _workflow(keyless_root, key=False)
    graphless_root = tmp_path / "b"
    graphless_root.mkdir()
    graphless = _workflow(graphless_root, graph=None)
    startless_root = tmp_path / "c"
    startless_root.mkdir()
    startless = _workflow(startless_root, graph="digraph g { a [shape=box] }")
    runs = [_run(f"r{i}", workflow=w) for i, w in enumerate((gone, keyless, graphless, startless))]
    attempts = attempts_from_runs(runs=runs, run_payload=reader)
    assert all(a.workflow_identity.startswith("unreadable-workflow:") for a in attempts)


def test_green_active_and_diagnosed_runs(tmp_path: Path) -> None:
    """A green run tops the graph; an active run is not complete; diagnosis is marked."""
    workflow = _workflow(tmp_path)

    def running(_factory: str, _run: str) -> object | None:
        return _payload(done=("implement",), failed=(), status="running")

    green = _run("g", workflow=workflow, status="green", detail="")
    green_blind = _run("gb", workflow=None, status="green", detail="")
    active = _run("a", workflow=workflow)
    unobservable = _run("u", workflow=workflow, status="run-unobservable", host=True)
    attempts = attempts_from_runs(
        runs=[green, green_blind, active, unobservable], run_payload=running
    )
    assert (attempts[0].high_water_milestone, attempts[0].high_water_order) == ("green", 6)
    assert attempts[0].terminal_cause == "green"
    assert attempts[1].high_water_order == 0
    assert [a.completed for a in attempts] == [True, True, False, False]
    marked = with_diagnosed(attempts=attempts, run_ids=frozenset({"a"}))
    assert [a.diagnosed for a in marked] == [False, False, True, False]


def test_an_unusable_payload_or_status_grades_nothing_reached(tmp_path: Path) -> None:
    """A payload that is no run record, or whose statuses are not text, reaches no milestone."""
    workflow = _workflow(tmp_path)
    payloads: dict[str, object] = {
        "r1": "not a run record",
        "r2": {"checkpoint": {"node_outcomes": {"implement": {"status": 5}}}},
    }
    attempts = attempts_from_runs(
        runs=[_run("r1", workflow=workflow), _run("r2", workflow=workflow)],
        run_payload=lambda _factory, run_id: payloads[run_id],
    )
    assert [attempt.high_water_order for attempt in attempts] == [-1, -1]
    assert [attempt.item_attributable for attempt in attempts] == [None, None]
