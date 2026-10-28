"""The in-loop human-gate outcome lives in its own cohesive module.

`_dispatcher_fabro_terminal` hit the hard LLOC ceiling when the recapture-cap
mapping was added, so the `blocked` gate concern moved out by cohesion. The module
is imported inside the test body so a missing module fails an assertion, not
collection.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_NEW_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_blocked_gate_outcome"
_SOURCE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal"


def test_the_blocked_gate_outcome_moved_to_its_own_module() -> None:
    assert (_COMMANDS / "_dispatcher_blocked_gate_outcome.py").is_file()
    new: Any = importlib.import_module(_NEW_MODULE)
    source: Any = importlib.import_module(_SOURCE_MODULE)

    assert new.__all__ == ["blocked_gate_outcome"]
    assert callable(new.blocked_gate_outcome)
    assert not hasattr(source, "_blocked_outcome")
    assert not hasattr(source, "_blocked_detail")
    assert source.blocked_gate_outcome is new.blocked_gate_outcome
