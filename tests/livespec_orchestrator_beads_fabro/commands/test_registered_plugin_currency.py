"""Currency warning command coverage for Scenario 271."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/registered_plugin_currency.py"
)
_WRAPPER = _REPO_ROOT / ".claude-plugin/scripts/bin/registered_plugin_currency.py"
_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"


def _write_json(*, path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value), encoding="utf-8")


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    assert _WRAPPER.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands.registered_plugin_currency"
    )


def test_warning_names_the_registered_and_latest_release_versions(tmp_path: Path) -> None:
    command = _module()
    project = tmp_path / "project"
    build = tmp_path / "build"
    release = tmp_path / "release"
    registry = tmp_path / "installed_plugins.json"
    marketplaces = tmp_path / "known_marketplaces.json"
    _write_json(path=build / "plugin.json", value={"version": "1.2.3"})
    _write_json(path=release / "plugin.json", value={"version": "1.2.4"})
    _write_json(
        path=registry,
        value={"plugins": {_KEY: [{"projectPath": str(project), "installPath": str(build)}]}},
    )
    _write_json(
        path=marketplaces,
        value={
            "livespec-orchestrator-beads-fabro": {
                "source": {"ref": "release"},
                "installLocation": str(release),
            }
        },
    )

    warning = command.registered_plugin_currency_warning(
        repo=project, install_record=registry, marketplace_record=marketplaces
    )

    assert warning is not None
    assert "1.2.3" in warning
    assert "1.2.4" in warning


def test_current_or_unregistered_projects_do_not_warn(tmp_path: Path) -> None:
    command = _module()
    project = tmp_path / "project"
    build = tmp_path / "build"
    registry = tmp_path / "installed_plugins.json"
    marketplaces = tmp_path / "known_marketplaces.json"
    _write_json(path=build / "plugin.json", value={"version": "1.2.4"})
    _write_json(
        path=registry,
        value={"plugins": {_KEY: [{"projectPath": str(project), "installPath": str(build)}]}},
    )
    _write_json(
        path=marketplaces,
        value={
            "livespec-orchestrator-beads-fabro": {
                "source": {"ref": "release"},
                "installLocation": str(build),
            }
        },
    )

    assert (
        command.registered_plugin_currency_warning(
            repo=project, install_record=registry, marketplace_record=marketplaces
        )
        is None
    )
    assert (
        command.registered_plugin_currency_warning(
            repo=tmp_path / "other", install_record=registry, marketplace_record=marketplaces
        )
        is None
    )
