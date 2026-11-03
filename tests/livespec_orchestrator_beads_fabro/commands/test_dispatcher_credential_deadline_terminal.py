"""Classifying credential-use guard endings before the Dispatcher disposes them."""

from __future__ import annotations

import importlib
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline_terminal"


def test_the_host_classifies_each_guard_ending_once_with_its_distinct_cause() -> None:
    """A startup refusal and a later refusal are not the same terminal fact."""
    assert (_COMMANDS / "_dispatcher_credential_deadline_terminal.py").is_file()
    terminal = importlib.import_module(_MODULE)

    assert (
        terminal.deadline_cause_from_guard_output(
            text="LIVESPEC_CREDENTIAL_DEADLINE_QUEUE_EXCEEDED\n"
        )
        == terminal.QUEUE_EXCEEDED_CAUSE
    )
    assert (
        terminal.deadline_cause_from_guard_output(
            text="LIVESPEC_CREDENTIAL_DEADLINE_LAUNCH_REFUSED\n"
        )
        == terminal.LAUNCH_REFUSED_CAUSE
    )
    assert (
        terminal.deadline_cause_from_guard_output(
            text="LIVESPEC_CREDENTIAL_DEADLINE_KILLED_MID_NODE\n"
        )
        == terminal.KILLED_MID_NODE_CAUSE
    )
    assert terminal.deadline_cause_from_guard_output(text="ordinary node failure") is None
