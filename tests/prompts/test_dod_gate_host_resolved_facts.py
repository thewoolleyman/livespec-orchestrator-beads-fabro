"""The gate rubric consumes the facts a tool-free host taking resolves for it.

A host taking offers no tool, so the capability set and the referenced heading
bodies arrive in the subject.  The shared rubric must name the subject block it
reads, in the words the renderer writes, or the judge keeps probing for files it
cannot reach.  PROMPT PROSE IS HARD-WRAPPED, so each needle sits within one line.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    CAPABILITIES_HEADING,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    UNPUBLISHED_REPORT,
)

_PROMPT = (
    Path(__file__).parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/prompts/dod-gate.md"
)


def test_the_rubric_names_the_capability_block_the_subject_carries() -> None:
    prompt = _PROMPT.read_text(encoding="utf-8")

    assert f"`{CAPABILITIES_HEADING}` block" in prompt
    assert "that block IS the" in prompt
    assert "do not look for the" in prompt
    assert f"`{UNPUBLISHED_REPORT}` verbatim" in prompt


def test_the_rubric_withholds_what_a_tool_free_judge_cannot_establish() -> None:
    prompt = _PROMPT.read_text(encoding="utf-8")

    assert "If you hold no tool that can read" in prompt
    assert "(this heading does not resolve in the governed spec tree)" in prompt
    assert "hold no tool that can search, you cannot establish that none governs" in prompt
