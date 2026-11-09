"""The gate prompt sends the node to the file the Dispatcher wrote the subject to.

The goal no longer carries the judgement subject (bd-ib-tzvtgc), so the prompt is
the only thing that tells the `dod_gate` node where the subject is. A prompt naming
a path the Dispatcher does not write is a prompt pointed at nothing, and it reads
exactly like a correct one -- which is why the path needle is IMPORTED from the
module that renders the step rather than retyped here.

PROMPT PROSE IS HARD-WRAPPED, so every needle is chosen to sit WITHIN one physical
line.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_subject import (
    dod_gate_subject_path_expansion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    HOST_ENDING_CONTRACT,
)

_PROMPT = (
    Path(__file__).parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/prompts/dod-gate.md"
)
_HOST_SUBJECT_HEADING = "## The work-item under judgement"


def _prompt() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def test_the_prompt_names_the_path_the_dispatcher_materializes_the_subject_at() -> None:
    assert dod_gate_subject_path_expansion() in _prompt()


def test_the_prompt_still_grades_the_subject_a_host_call_appends() -> None:
    assert _HOST_SUBJECT_HEADING in HOST_ENDING_CONTRACT
    assert _HOST_SUBJECT_HEADING in _prompt()


def test_the_prompt_says_how_an_unreadable_subject_is_reported() -> None:
    assert "`dod-gate-subject: unreadable`" in _prompt()
