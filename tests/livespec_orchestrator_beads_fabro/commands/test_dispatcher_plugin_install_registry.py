"""Reading this plugin's install records out of the host's Claude Code registry.

The ONE reader of `installed_plugins.json`, shared by the registered-install
currency finding and by the host-wide sandbox-image enumeration. What is
asserted here is the pair each usable record yields, that another plugin's
records are not this plugin's, and that EVERY malformed shape is dropped rather
than refused — the posture the file's provenance requires, since it is written
by the harness and a shape this build has not seen is a harness version rather
than an operator error.

Each malformed case sits BESIDE a usable record in the same registry, so a
reader that had stopped reading the file altogether would fail them instead of
satisfying them: "the bad row was dropped" and "nothing was read" are the same
observation when the only row is the bad one.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    PluginInstallRecord,
    plugin_install_records,
)

_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_SECOND_MARKETPLACE_KEY = "livespec-orchestrator-beads-fabro@a-second-marketplace"
_OTHER_PLUGIN_KEY = "some-other-plugin@its-own-marketplace"
_NOT_UTF8 = b'\xff\xfe{"plugins": {}}'


def _registry(*, path: Path, document: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _usable(*, project: str, install: str) -> dict[str, str]:
    return {"projectPath": project, "installPath": install}


def test_every_usable_record_of_this_plugin_is_read_in_registry_order(tmp_path: Path) -> None:
    """A record pairs the governed project root with the build the registry resolves."""
    registry = _registry(
        path=tmp_path / "installed_plugins.json",
        document={
            "plugins": {
                _PLUGIN_KEY: [_usable(project="/repos/first", install="/cache/one")],
                _SECOND_MARKETPLACE_KEY: [_usable(project="/repos/second", install="/cache/two")],
            }
        },
    )

    assert plugin_install_records(install_record=registry) == (
        PluginInstallRecord(project_path=Path("/repos/first"), install_path=Path("/cache/one")),
        PluginInstallRecord(project_path=Path("/repos/second"), install_path=Path("/cache/two")),
    )


def test_another_plugins_records_are_not_this_plugins(tmp_path: Path) -> None:
    """The plugin is matched on the part before the marketplace separator, exactly."""
    registry = _registry(
        path=tmp_path / "installed_plugins.json",
        document={
            "plugins": {
                _OTHER_PLUGIN_KEY: [_usable(project="/repos/theirs", install="/cache/theirs")],
                _PLUGIN_KEY: [_usable(project="/repos/ours", install="/cache/ours")],
            }
        },
    )

    assert plugin_install_records(install_record=registry) == (
        PluginInstallRecord(project_path=Path("/repos/ours"), install_path=Path("/cache/ours")),
    )


def test_a_malformed_record_is_dropped_and_its_sound_siblings_are_kept(tmp_path: Path) -> None:
    """A non-object entry, a missing key, a wrong type and an empty value each drop."""
    registry = _registry(
        path=tmp_path / "installed_plugins.json",
        document={
            "plugins": {
                _PLUGIN_KEY: [
                    "not-an-object",
                    {"installPath": "/cache/no-project"},
                    _usable(project="", install="/cache/empty-project"),
                    _usable(project="/repos/empty-install", install=""),
                    {"projectPath": "/repos/wrong-type", "installPath": 7},
                    _usable(project="/repos/sound", install="/cache/sound"),
                ]
            }
        },
    )

    assert plugin_install_records(install_record=registry) == (
        PluginInstallRecord(project_path=Path("/repos/sound"), install_path=Path("/cache/sound")),
    )


def test_a_non_list_entry_group_is_dropped_and_its_sound_sibling_is_kept(tmp_path: Path) -> None:
    """One key holding something other than a list of records says nothing about the others."""
    registry = _registry(
        path=tmp_path / "installed_plugins.json",
        document={
            "plugins": {
                _SECOND_MARKETPLACE_KEY: {"projectPath": "/repos/mapped"},
                _PLUGIN_KEY: [_usable(project="/repos/sound", install="/cache/sound")],
            }
        },
    )

    assert plugin_install_records(install_record=registry) == (
        PluginInstallRecord(project_path=Path("/repos/sound"), install_path=Path("/cache/sound")),
    )


def test_a_registry_that_declares_no_plugins_mapping_reads_as_no_records(tmp_path: Path) -> None:
    """A `plugins` key of the wrong shape is an empty read, never a refusal."""
    registry = _registry(path=tmp_path / "installed_plugins.json", document={"plugins": []})

    assert plugin_install_records(install_record=registry) == ()


def test_a_registry_whose_root_is_not_an_object_reads_as_no_records(tmp_path: Path) -> None:
    """A document that parses to something other than an object carries no records."""
    registry = _registry(path=tmp_path / "installed_plugins.json", document=["plugins"])

    assert plugin_install_records(install_record=registry) == ()


def test_a_registry_that_does_not_parse_reads_as_no_records(tmp_path: Path) -> None:
    """Invalid JSON is an empty read: the file is the harness's, not this fleet's."""
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text('{"plugins": ', encoding="utf-8")

    assert plugin_install_records(install_record=registry) == ()


def test_a_registry_that_cannot_be_read_reads_as_no_records(tmp_path: Path) -> None:
    """Bytes that are not UTF-8 are an empty read for the same reason."""
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_bytes(_NOT_UTF8)

    assert plugin_install_records(install_record=registry) == ()


def test_an_absent_registry_reads_as_no_records(tmp_path: Path) -> None:
    """A host with no registry governs no repositories through it."""
    assert plugin_install_records(install_record=tmp_path / "absent.json") == ()
