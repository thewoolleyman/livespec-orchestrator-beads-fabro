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
    assert module.__all__ == ["PostRunTerminal", "post_run_terminal"]


def test_the_engine_no_longer_carries_the_names_the_post_run_path_moved_out() -> None:
    _post_run_module()
    engine = importlib.import_module(f"{_PACKAGE}._dispatcher_engine")

    still_in_engine = [name for name in _MOVED_OUT_OF_THE_ENGINE if hasattr(engine, name)]

    assert still_in_engine == []
