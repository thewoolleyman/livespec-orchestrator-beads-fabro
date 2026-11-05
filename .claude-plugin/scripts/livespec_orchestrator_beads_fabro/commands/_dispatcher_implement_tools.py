"""Assemble the sandbox programs the separate Red and Green nodes use."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner import (
    commit_runner_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program import (
    gate_preview_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_guard import (
    review_guard_prepare_steps_block,
)

__all__: list[str] = ["implement_tool_prepare_steps_block"]


def implement_tool_prepare_steps_block() -> str:
    """Materialize the commit runner, preview, and review guard in their required order."""
    return (
        commit_runner_prepare_steps_block()
        + gate_preview_prepare_steps_block()
        + review_guard_prepare_steps_block()
    )
