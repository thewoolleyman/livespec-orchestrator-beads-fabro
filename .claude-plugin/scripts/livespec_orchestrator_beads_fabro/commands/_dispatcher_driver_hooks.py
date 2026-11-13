"""Named prepare-step projections for the two factory Driver plugins."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_driver_hooks_claude import (
    claude_materialize_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_driver_hooks_codex import (
    codex_materialize_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PrepareStep,
    render_prepare_step,
)

__all__: list[str] = [
    "claude_driver_hooks_prepare_steps_block",
    "codex_driver_hooks_prepare_steps_block",
]


def claude_driver_hooks_prepare_steps_block() -> str:
    """Render the release-pinned Claude Driver cache materialization step."""
    return _prepare_block(label="Claude", script=claude_materialize_script())


def codex_driver_hooks_prepare_steps_block() -> str:
    """Render Codex's release-byte verified hook-trust materialization step."""
    return _prepare_block(label="Codex", script=codex_materialize_script())


def _prepare_block(*, label: str, script: str) -> str:
    """Give the runtime-specific script its stable dispatcher-owned step header."""
    header = (
        f"\n# --- Dispatcher-materialized {label} Driver hooks: pin the release"
        "\n# --- before the adapter starts its sandbox turn ---\n"
    )
    if label == "Claude":
        header += '# --- its marketplace registry records "ref": revision for this run ---\n'
    if label == "Codex":
        header += "# --- newer Codex records trusted_content_hash after byte verification ---\n"
    return header + render_prepare_step(step=PrepareStep(script=script))
