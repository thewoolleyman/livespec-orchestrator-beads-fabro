"""The per-poll budget-then-stall decision lives in its own module, not in the launcher.

Work-item bd-ib-pwcqpr, the first slice of the pre-approved split of
bd-ib-pxp2ve: a NO-BEHAVIOUR-CHANGE extraction that makes room in the watched
launcher a run-watch fix must thread state through. The decision a poll takes
about a live run -- the whole-run wall budget verdict taking precedence over the
stall decision -- is one question, and it is cut out at that concern's public
entry point so a later observer can ask the same question instead of duplicating
it.

Behaviour is graded by the launcher's own existing watch-loop tests (the budget
cancel, the held export and the stall cancel), which drive this decision through
the loop unchanged; this file grades only WHERE the decision lives.
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
_MODULE = "_dispatcher_run_watch_decision"
_MOVED_OUT_OF_THE_LAUNCHER = (
    "RunWallVerdict",
    "StallVerdict",
    "decide_stall",
    "cancel_stalled_run",
    "quiet_window_seconds",
)


def _decision_module() -> Any:
    """Import the per-poll decision module, proving its file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def test_the_per_poll_decision_is_a_public_entry_point_of_its_own_module() -> None:
    module = _decision_module()

    assert callable(module.decide_run_watch)
    assert module.__all__ == [
        "ReattachRun",
        "RunWatchDecision",
        "RunWatchState",
        "decide_run_watch",
    ]


def test_the_launcher_no_longer_carries_the_names_the_decision_moved_out() -> None:
    _decision_module()
    launcher = importlib.import_module(f"{_PACKAGE}._dispatcher_io_fabro_launcher")

    still_in_launcher = [name for name in _MOVED_OUT_OF_THE_LAUNCHER if hasattr(launcher, name)]

    assert still_in_launcher == []
