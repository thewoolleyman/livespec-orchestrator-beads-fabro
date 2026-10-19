"""The whole-run wall budget's pre-dispatch admission (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Whole-run wall
budget key": "A resolved budget smaller than any node timeout resolved for the
same dispatch MUST be rejected before any run exists, naming both keys and both
values, because such a budget would cancel that node's legitimate turn."

The refusal is graded where the node timeouts are already resolved and
rendered, so the conflict is measured against the values the graph actually
received rather than against a re-derivation of them -- and the budget rides
the same payload and the same plan the timeouts do, resolved from ONE read of
the dispatch target's configuration.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_args import (
    add_dispatch_common,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    prepare_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    DEFAULT_RUN_WALL_BUDGET,
    RUN_WALL_BUDGET_KEY,
    RunWallBudget,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget"
_NODE_TIMEOUTS_KEY = "dispatcher.node_timeouts"
_COMMITTED_WORKFLOW_TOML = '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n'
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="14400s"\n'
    '        prompt="@prompts/implement.md"\n'
    "    ]\n"
    "\n"
    "    janitor [\n"
    '        timeout="3600s"\n'
    "    ]\n"
    "}\n"
)


class _RecordingJournal:
    """Minimal JournalWriter seam that keeps every appended record."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _conflict() -> Any:
    """The conflict refusal, reached through the module it belongs to."""
    module = importlib.import_module(_MODULE)
    assert hasattr(module, "node_timeout_conflict"), f"{_MODULE} declares no node_timeout_conflict"
    return module.node_timeout_conflict


def _committed_workflow(*, root: Path) -> Path:
    workflow_dir = root / "workflow"
    prompts = workflow_dir / "prompts"
    prompts.mkdir(parents=True)
    _ = (prompts / "implement.md").write_text("implement prompt\n", encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    committed = workflow_dir / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return committed


def _write_dispatcher_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _prepared(
    *,
    tmp_path: Path,
    dispatcher: dict[str, object],
    argument: str | None = None,
) -> tuple[WorkflowPayload | str, _RecordingJournal]:
    committed = _committed_workflow(root=tmp_path)
    _write_dispatcher_config(cwd=tmp_path, dispatcher=dispatcher)
    journal = _RecordingJournal()
    prepared = prepare_workflow_payload(
        repo=tmp_path,
        committed=committed,
        payload_dir=tmp_path / "payload",
        journal=cast("Any", journal),
        work_item_id="bd-ib-sdxfsn",
        adapters={},
        run_wall_budget_argument=argument,
    )
    return prepared, journal


def test_a_budget_at_or_above_every_node_timeout_does_not_conflict() -> None:
    """Equality passes: a budget EQUAL to the longest node is not smaller than it."""
    conflict = _conflict()
    budget = RunWallBudget(seconds=3600.0, layer=WORKFLOW_DEFAULT_LAYER)
    assert conflict(budget=budget, nodes={"implement": 3600, "janitor": 1800}) is None
    assert conflict(budget=budget, nodes={}) is None


def test_a_budget_below_a_node_timeout_names_both_keys_and_both_values() -> None:
    """The refusal names the budget key and value AND the node key and value."""
    conflict = _conflict()
    refusal = conflict(
        budget=RunWallBudget(seconds=1800.0, layer=REPOSITORY_LAYER),
        nodes={"implement": 3600, "janitor": 2400},
    )
    assert isinstance(refusal, str)
    assert RUN_WALL_BUDGET_KEY in refusal
    assert "1800" in refusal
    # The LONGEST offending node is the binding constraint, so it is the one
    # named: a refusal naming `janitor` would send an operator to raise a
    # budget that `implement` would still exceed.
    assert f"{_NODE_TIMEOUTS_KEY}.implement" in refusal
    assert "3600" in refusal
    assert "janitor" not in refusal


def test_the_offending_node_is_resolved_deterministically_on_a_tie() -> None:
    """Two nodes at the same offending value resolve to one named node.

    Deterministic because the population is walked in sorted node order, so a
    tie names the alphabetically-first node rather than whichever one the
    mapping happened to yield first.
    """
    conflict = _conflict()
    refusal = conflict(
        budget=RunWallBudget(seconds=900.0, layer=REPOSITORY_LAYER),
        nodes={"review": 3600, "implement": 3600},
    )
    assert isinstance(refusal, str)
    assert f"{_NODE_TIMEOUTS_KEY}.implement" in refusal


def test_preparing_the_payload_refuses_a_budget_below_a_rendered_node_timeout(
    tmp_path: Path,
) -> None:
    """The refusal lands before any run exists, and journals no record."""
    prepared, journal = _prepared(
        tmp_path=tmp_path,
        dispatcher={
            "run_wall_budget_seconds": 1800,
            "node_timeouts": {"implement": 3600},
        },
    )
    assert isinstance(prepared, str)
    assert RUN_WALL_BUDGET_KEY in prepared
    assert f"{_NODE_TIMEOUTS_KEY}.implement" in prepared
    assert journal.records == []


def test_preparing_the_payload_refuses_an_invalid_committed_budget(tmp_path: Path) -> None:
    """A non-positive committed budget refuses, naming the key, before any run."""
    prepared, journal = _prepared(tmp_path=tmp_path, dispatcher={"run_wall_budget_seconds": 0})
    assert isinstance(prepared, str)
    assert RUN_WALL_BUDGET_KEY in prepared
    assert journal.records == []


def test_preparing_the_payload_journals_the_budget_beside_the_node_timeouts(
    tmp_path: Path,
) -> None:
    """The dispatch record carries the resolved budget and its supplying layer."""
    prepared, journal = _prepared(tmp_path=tmp_path, dispatcher={})
    assert isinstance(prepared, WorkflowPayload)
    assert prepared.run_wall_budget == DEFAULT_RUN_WALL_BUDGET
    assert len(journal.records) == 1
    assert journal.records[0]["run_wall_budget"] == {
        "seconds": 21600.0,
        "layer": WORKFLOW_DEFAULT_LAYER,
    }
    # Beside, not instead of: one read of the file resolved both.
    assert "node_timeouts" in journal.records[0]


def test_the_per_dispatch_argument_reaches_the_prepared_payload(tmp_path: Path) -> None:
    """The argument layer is wired end to end, not merely resolvable."""
    prepared, journal = _prepared(
        tmp_path=tmp_path,
        dispatcher={"run_wall_budget_seconds": 25200},
        argument="28800",
    )
    assert isinstance(prepared, WorkflowPayload)
    assert prepared.run_wall_budget.seconds == 28800.0
    assert journal.records[0]["run_wall_budget"] == {
        "seconds": 28800.0,
        "layer": "per-dispatch argument",
    }


def test_the_dispatch_argument_surface_declares_the_budget_override() -> None:
    """Every dispatching subcommand accepts `--run-wall-budget-seconds`.

    An ARGUMENT and never an environment variable, for the reason `--acp-node`
    is: an ad-hoc shell must not re-budget the factory with nothing in the
    journal to show for it.
    """
    parser = argparse.ArgumentParser()
    add_dispatch_common(parser=parser)
    args = parser.parse_args(["--repo", "/tmp", "--run-wall-budget-seconds", "28800"])
    assert args.run_wall_budget_seconds == "28800"
    assert parser.parse_args(["--repo", "/tmp"]).run_wall_budget_seconds is None


def test_the_plan_carries_the_resolved_budget(tmp_path: Path) -> None:
    """The budget rides `DispatchPlan` exactly as the stall window does."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-sdxfsn",
        workflow_toml=tmp_path / "overlay.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
        run_wall_budget=RunWallBudget(seconds=25200.0, layer=REPOSITORY_LAYER),
    )
    assert plan.run_wall_budget == RunWallBudget(seconds=25200.0, layer=REPOSITORY_LAYER)
    unconfigured = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-sdxfsn",
        workflow_toml=tmp_path / "overlay.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    assert unconfigured.run_wall_budget == DEFAULT_RUN_WALL_BUDGET
