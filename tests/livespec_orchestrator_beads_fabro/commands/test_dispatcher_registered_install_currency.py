"""Tests for the registered-install currency verdict (bd-ib-h3mm).

The verdict compares the build a SESSION executes against the build the
dispatch target's install registry records, so a session that bound its
plugin root before the last `claude plugin update` is named as lagging --
and named with a restart remedy, because an update cannot move a running
session (bd-ib-97v4).
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_registered_install_currency import (
    REGISTERED_INSTALL_LAG_STAGE,
    registered_install_verdict,
)

_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"


def _build(*, root: Path, version: str, flattened: bool = True) -> Path:
    """A materialized build: the manifest at the build root (cache) or under `.claude-plugin/`."""
    manifest = root / "plugin.json" if flattened else root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _ = manifest.write_text(json.dumps({"name": "x", "version": version}), encoding="utf-8")
    return root


def _registry(*, path: Path, entries: list[dict[str, str]], key: str = _PLUGIN_KEY) -> Path:
    _ = path.write_text(json.dumps({"version": 2, "plugins": {key: entries}}), encoding="utf-8")
    return path


def test_older_executing_build_lags_with_a_restart_remedy(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(
        path=tmp_path / "installed_plugins.json",
        entries=[{"projectPath": str(repo), "installPath": str(registered)}],
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.undetermined_detail is None
    assert verdict.lag_detail is not None
    assert "0.124.1" in verdict.lag_detail
    assert "0.129.1" in verdict.lag_detail
    assert "Restart the session" in verdict.lag_detail
    assert "surfaced, not enforced" in verdict.lag_detail
    assert "dispatcher.minimum_release" in verdict.lag_detail
    assert REGISTERED_INSTALL_LAG_STAGE == "dispatcher-registered-install-lag"


def test_same_build_is_current(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    build = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(
        path=tmp_path / "installed_plugins.json",
        entries=[{"projectPath": str(repo), "installPath": str(build)}],
    )

    verdict = registered_install_verdict(plugin_root=build, repo=repo, install_record=record)

    assert verdict.lag_detail is None
    assert verdict.undetermined_detail is None


def test_newer_executing_build_is_surfaced_naming_both_builds(tmp_path: Path) -> None:
    """A primary-checkout root ahead of the registered cache build runs an unadopted build."""
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "checkout", version="0.131.0", flattened=False)
    registered = _build(root=tmp_path / "b9a4004480ab", version="0.130.1")
    record = _registry(
        path=tmp_path / "installed_plugins.json",
        entries=[{"projectPath": str(repo), "installPath": str(registered)}],
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.undetermined_detail is None
    assert verdict.lag_detail is not None
    assert "0.131.0" in verdict.lag_detail
    assert "0.130.1" in verdict.lag_detail
    assert "newer" in verdict.lag_detail
    assert "surfaced, not enforced" in verdict.lag_detail
    assert "just adopt-orchestrator-build <clone> <build>" in verdict.lag_detail
    assert "claude plugin update" not in verdict.lag_detail


def test_missing_registry_is_undetermined_not_current(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")

    verdict = registered_install_verdict(
        plugin_root=executing, repo=repo, install_record=tmp_path / "absent.json"
    )

    assert verdict.lag_detail is None
    assert verdict.undetermined_detail is not None
    assert "no registered install" in verdict.undetermined_detail
    assert "absent.json" in verdict.undetermined_detail


def test_malformed_registry_is_undetermined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    record = tmp_path / "installed_plugins.json"
    _ = record.write_text("{not json", encoding="utf-8")

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.lag_detail is None
    assert verdict.undetermined_detail is not None


def test_registry_that_is_a_json_list_is_undetermined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    record = tmp_path / "installed_plugins.json"
    _ = record.write_text("[]", encoding="utf-8")

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.undetermined_detail is not None


def test_undecodable_registry_is_undetermined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    record = tmp_path / "installed_plugins.json"
    _ = record.write_bytes(b"\xff\xfe\x00\x01")

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.undetermined_detail is not None


def test_registry_without_an_entry_for_the_repo_is_undetermined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(
        path=tmp_path / "installed_plugins.json",
        entries=[
            {"projectPath": str(other), "installPath": str(registered)},
            {"projectPath": "", "installPath": str(registered)},
            {"installPath": str(registered)},
        ],
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.lag_detail is None
    assert verdict.undetermined_detail is not None
    assert "no registered install" in verdict.undetermined_detail


def test_entries_under_another_plugin_key_or_non_list_are_ignored(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = tmp_path / "installed_plugins.json"
    _ = record.write_text(
        json.dumps(
            {
                "plugins": {
                    "livespec@livespec": [
                        {"projectPath": str(repo), "installPath": str(registered)}
                    ],
                    _PLUGIN_KEY: {"projectPath": str(repo), "installPath": str(registered)},
                }
            }
        ),
        encoding="utf-8",
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.undetermined_detail is not None


def test_non_object_entry_is_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = tmp_path / "installed_plugins.json"
    _ = record.write_text(
        json.dumps(
            {
                "plugins": {
                    _PLUGIN_KEY: [
                        "not-a-record",
                        {"projectPath": str(repo), "installPath": str(registered)},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.lag_detail is not None


def test_unparseable_registered_manifest_is_undetermined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = _build(root=tmp_path / "d709f27ac3c1", version="0.124.1")
    registered = tmp_path / "6edebb0b0c50"
    registered.mkdir()
    record = _registry(
        path=tmp_path / "installed_plugins.json",
        entries=[{"projectPath": str(repo), "installPath": str(registered)}],
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.lag_detail is None
    assert verdict.undetermined_detail is not None
    assert "manifest did not parse" in verdict.undetermined_detail


def test_unparseable_executing_manifest_is_undetermined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executing = tmp_path / "unknown-root"
    executing.mkdir()
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(
        path=tmp_path / "installed_plugins.json",
        entries=[{"projectPath": str(repo), "installPath": str(registered)}],
    )

    verdict = registered_install_verdict(plugin_root=executing, repo=repo, install_record=record)

    assert verdict.undetermined_detail is not None
