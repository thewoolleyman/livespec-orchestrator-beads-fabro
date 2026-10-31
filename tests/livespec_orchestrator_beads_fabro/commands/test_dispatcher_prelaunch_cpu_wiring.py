"""The dispatch launch path profiles every CPU-bearing pre-launch phase."""

from __future__ import annotations

from pathlib import Path

_DISPATCH_LOOP = (
    Path(__file__).parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_loop.py"
)


def test_the_launch_path_names_the_profiled_prelaunch_phases() -> None:
    """A source-only profile would leave the operational launch path dark."""
    source = _DISPATCH_LOOP.read_text(encoding="utf-8")

    assert "PrelaunchCpuProfile" in source
    for phase in (
        "record-dispatch",
        "github-app-auth",
        "goal-minijinja-preflight",
        "factory-auth",
        "run-config-overlay",
        "goal-render",
    ):
        assert f'name="{phase}"' in source
