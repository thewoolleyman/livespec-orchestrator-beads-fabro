"""The watched launch's result mapping lives in its own module, not in the launcher.

Work-item bd-ib-pwcqpr: the second extraction that makes room in the watched
launcher. Mapping how a watch loop ended (a reaped item, a run cancelled past its
whole-run wall budget, a stalled run, or the run's own return) onto the
`FabroRunResult` the engine reads is one concern, cut at its public entry point.
Behaviour is graded by the launcher's existing tests; this file grades only WHERE
the mapping lives.
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
_MODULE = "_dispatcher_watched_launch_result"


def _result_module() -> Any:
    """Import the watched-launch result module, proving its file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def test_the_watched_launch_result_is_a_public_entry_point_of_its_own_module() -> None:
    module = _result_module()

    assert callable(module.watched_launch_result)
    assert module.__all__ == ["WatchResult", "watched_launch_result"]


def test_the_launcher_no_longer_carries_the_private_watch_result() -> None:
    _result_module()
    launcher = importlib.import_module(f"{_PACKAGE}._dispatcher_io_fabro_launcher")

    assert not hasattr(launcher, "_WatchResult")
    assert not hasattr(launcher, "FABRO_RM_TIMEOUT_SECONDS")
