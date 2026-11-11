"""The post-run terminal path lives in its own module, not in the dispatch engine.

Work-item bd-ib-pwcqpr, the first slice of the pre-approved split of
bd-ib-pxp2ve: a NO-BEHAVIOUR-CHANGE extraction that makes room in the engine
module a run-watch fix must thread state through. Everything `run_dispatch` does
from observing the run after the client returns through the terminal
publication's refusal belongs to one concern, and it is cut at that concern's
public entry point rather than at a line count.

Behaviour is graded by the engine's own existing dispatch tests, which drive
this path through `run_dispatch` unchanged; this file grades only WHERE the code
lives, so the room the next change needs cannot quietly be spent again.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_run_terminal import (
    reattach_terminal,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_dispatcher_post_run_terminal"
_MOVED_OUT_OF_THE_ENGINE = (
    "inspect_after_run",
    "journal_run_output_markers",
    "fabro_run_terminal_outcome",
    "worker_exit_engine_failure_outcome",
    "successful_store_loss_evidence",
    "reconcile_terminal_publication",
    "attach_node_timeout_cut",
)


def _post_run_module() -> Any:
    """Import the post-run terminal module, proving its file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def test_the_post_run_terminal_path_is_a_public_entry_point_of_its_own_module() -> None:
    module = _post_run_module()

    assert callable(module.post_run_terminal)
    assert module.__all__ == ["PostRunTerminal", "post_run_terminal", "reattach_terminal"]


def test_the_engine_no_longer_carries_the_names_the_post_run_path_moved_out() -> None:
    _post_run_module()
    engine = importlib.import_module(f"{_PACKAGE}._dispatcher_engine")

    still_in_engine = [name for name in _MOVED_OUT_OF_THE_ENGINE if hasattr(engine, name)]

    assert still_in_engine == []


def test_reattach_terminal_maps_budget_and_stall_cancels(tmp_path: Path) -> None:
    """A re-attach cancel retains the disposition selected by the shared watch."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-pxp2ve",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    command = CommandResult(exit_code=0, stdout="", stderr="")
    budget = reattach_terminal(
        plan=plan,
        inspect=FabroInspectResult(
            command=command,
            payload=None,
            status_kind="running",
            failure=None,
            budget_exceeded_run_id="01BUDGET",
        ),
    )
    stalled = reattach_terminal(
        plan=plan,
        inspect=FabroInspectResult(
            command=command,
            payload=None,
            status_kind="running",
            failure=None,
            stalled_run_id="01STALL",
        ),
    )

    assert budget is not None
    assert (budget.status, budget.fabro_run_id) == ("run-wall-budget-exceeded", "01BUDGET")
    assert stalled is not None
    assert (stalled.status, stalled.fabro_run_id) == ("stalled-no-progress", "01STALL")
    assert reattach_terminal(plan=plan, inspect=None) is None
