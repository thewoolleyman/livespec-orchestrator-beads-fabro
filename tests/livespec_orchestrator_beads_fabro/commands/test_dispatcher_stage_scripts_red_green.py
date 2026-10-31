"""The stage-script externalization module is shipped with the plugin."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_stage_script_externalization_module_is_present() -> None:
    """The dispatch payload can import the externalization seam."""
    plugin_root = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts"
    module_path = (
        plugin_root
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_dispatcher_stage_scripts.py"
    )
    assert module_path.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_stage_scripts"
    )
    assert "externalize_stage_scripts" in module.__all__
