"""Committed per-cycle runtime-ceiling configuration resolution."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config_cycle_ceilings import (
    resolve_adopted_cycle_ceilings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    NO_ADOPTED_CYCLE_CEILINGS,
)


def test_resolution_preserves_an_unadopted_policy_as_a_valid_empty_pair(tmp_path: Path) -> None:
    """No declared ceiling is distinct from an unreadable or invalid policy."""
    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{}}}', encoding="utf-8"
    )

    assert resolve_adopted_cycle_ceilings(cwd=tmp_path) == NO_ADOPTED_CYCLE_CEILINGS
