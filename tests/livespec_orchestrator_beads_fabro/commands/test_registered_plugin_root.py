"""The bundled registered-plugin-root command (Scenario 271)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMAND_MODULE = (
    _REPO_ROOT
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/registered_plugin_root.py"
)
_WRAPPER = _REPO_ROOT / ".claude-plugin/scripts/bin/registered_plugin_root.py"
_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"


def _registry(*, path: Path, entries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True)
    _ = path.write_text(json.dumps({"plugins": {_PLUGIN_KEY: entries}}), encoding="utf-8")


def test_command_prints_only_the_governed_projects_registered_plugin_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command follows the project's registry entry, never its own cache root."""
    assert _COMMAND_MODULE.is_file()
    assert _WRAPPER.is_file()
    command = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands.registered_plugin_root"
    )
    first_project = tmp_path / "first-project"
    second_project = tmp_path / "second-project"
    first_root = tmp_path / "first-build"
    second_root = tmp_path / "second-build"
    registry = tmp_path / "home/.claude/plugins/installed_plugins.json"
    _registry(
        path=registry,
        entries=[
            {"projectPath": str(first_project), "installPath": str(first_root)},
            {"projectPath": str(second_project), "installPath": str(second_root)},
        ],
    )
    monkeypatch.setattr(command, "default_plugin_install_registry", lambda: registry)

    assert command.main(argv=["--repo", str(second_project)]) == 0

    assert capsys.readouterr().out == f"{second_root}\n"


def test_command_refuses_a_project_without_a_registered_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing registry entry is actionable rather than falling back to this session."""
    assert _COMMAND_MODULE.is_file()
    command = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands.registered_plugin_root"
    )
    registry = tmp_path / "home/.claude/plugins/installed_plugins.json"
    _registry(path=registry, entries=[])
    monkeypatch.setattr(command, "default_plugin_install_registry", lambda: registry)

    assert command.main(argv=["--repo", str(tmp_path / "unregistered")]) != 0

    assert "no registered install" in capsys.readouterr().err
