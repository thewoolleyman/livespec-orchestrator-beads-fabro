"""Tests for the release-adoption needs-attention lane.

THIS SUITE CARRIES A POSITIVE CONTROL, and it is the load-bearing part. The
lane reports an ABSENCE — adopters that have NOT taken the current release — so
a reading that has quietly stopped working is indistinguishable from a healthy
fleet: both render as "nothing to report". `_positive_control_bases` therefore
plants an adopter that IS current with a KNOWN expected verdict, and
`test_positive_control_reports_a_current_adopter_as_current` fails the build
whenever the lane reports no current adopter against that fixture. Without it, a
mis-aimed registry read or an unparsed manifest would make the fact permanently
report that everyone is current.
"""

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    ReleaseAdoptionBases,
    adopter_resolutions,
    read_build_version,
    release_adoption_items,
    release_tip_version,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    __all__ as release_adoption_all,
)
from livespec_orchestrator_beads_fabro.commands.needs_attention import render_json
from livespec_runtime.attention_item import AttentionItem, validate_attention_item_id

_PLUGIN = "livespec-orchestrator-beads-fabro"
# What a real governed repository's own manifest names: ITSELF, never this
# plugin. Every fixture below runs the lane from such a repository on purpose.
_GOVERNED_PROJECT_PLUGIN = "livespec-overseer"
_TIP_VERSION = "0.84.2"
_STALE_VERSION = "0.84.0"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def _bundle_manifest(root: Path, *, version: str, name: str = _PLUGIN) -> Path:
    """A build carrying its manifest in the `.claude-plugin/` bundle directory."""
    _write_json(root / ".claude-plugin" / "plugin.json", {"name": name, "version": version})
    return root


def _flat_manifest(root: Path, *, version: str, name: str = _PLUGIN) -> Path:
    """A build carrying its manifest at the build root (where it moved to)."""
    _write_json(root / "plugin.json", {"name": name, "version": version})
    return root


def _project_root(tmp_path: Path) -> Path:
    """A governed repository — whose OWN manifest names a DIFFERENT plugin.

    That is deliberate, and every test in this file inherits it. The adoption
    question is about THIS plugin's builds, so the name keyed into the install
    registry must come from this plugin's own identity and never from whichever
    repository the lane happens to be running inside. A fixture whose project
    manifest named this plugin would mask the difference entirely: it makes a
    project-root read and an identity constant indistinguishable, while no real
    governed project — `livespec-overseer`, `homelab`, `livespec-runtime` —
    carries this plugin's name in its own manifest.
    """
    return _bundle_manifest(tmp_path / "project", version="0.84.2", name=_GOVERNED_PROJECT_PLUGIN)


def _marketplace(tmp_path: Path, *, version: str | None, ref: str = "release") -> Path:
    """A marketplace registry pointing at a clone checked out at `ref`."""
    clone = tmp_path / "marketplaces" / _PLUGIN
    if version is not None:
        _ = _bundle_manifest(clone, version=version)
    record = tmp_path / "known_marketplaces.json"
    _write_json(
        record,
        {
            _PLUGIN: {
                "source": {"source": "github", "repo": "x/y", "ref": ref},
                "installLocation": str(clone),
            }
        },
    )
    return record


def _install_record(tmp_path: Path, *, entries: object) -> Path:
    record = tmp_path / "installed_plugins.json"
    _write_json(record, {"version": 2, "plugins": {f"{_PLUGIN}@{_PLUGIN}": entries}})
    return record


def _positive_control_bases(tmp_path: Path) -> ReleaseAdoptionBases:
    """A host with ONE adopter on the release tip and ONE adopter behind it.

    The current adopter is the positive control: its expected verdict is known
    in advance, so the lane MUST name it and MUST call it current. The behind
    adopter is what forces the lane to compose at all — an all-current host is
    deliberately silent.
    """
    current_build = _flat_manifest(tmp_path / "builds" / "a1b2c3d4e5f6", version=_TIP_VERSION)
    stale_build = _bundle_manifest(tmp_path / "builds" / "f6e5d4c3b2a1", version=_STALE_VERSION)
    return ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {
                    "projectPath": str(tmp_path / "projects" / "adopter-current"),
                    "installPath": str(current_build),
                },
                {
                    "projectPath": str(tmp_path / "projects" / "adopter-behind"),
                    "installPath": str(stale_build),
                },
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )


def _items(tmp_path: Path, *, bases: ReleaseAdoptionBases) -> list[AttentionItem]:
    return release_adoption_items(
        project_root=_project_root(tmp_path), repo="repo-under-test", bases=bases
    )


def _summary_for(items: list[AttentionItem], *, adopter: str) -> str:
    matches = [item for item in items if item.id == f"hygiene:release-adoption:{adopter}"]
    assert len(matches) == 1, f"expected exactly one item for {adopter}, got {len(matches)}"
    return matches[0].summary


def test_public_surface_names_are_non_private() -> None:
    assert release_adoption_all == [
        "AdopterResolution",
        "ReleaseAdoptionBases",
        "adopter_resolutions",
        "default_release_adoption_bases",
        "read_build_version",
        "release_adoption_items",
        "release_tip_version",
    ]
    assert all(not name.startswith("_") for name in release_adoption_all)


def test_adopters_resolve_under_this_plugins_name_not_the_governed_projects(
    tmp_path: Path,
) -> None:
    """The install-registry key is THIS plugin's name, wherever the lane runs.

    A governed project's `.claude-plugin/plugin.json` names that project, so
    deriving the lookup key from the project root queries a registry key that
    does not exist. The lane then finds no adopters and emits nothing — an
    all-clear manufactured out of a mis-aimed read, which is precisely the
    silent failure this fact exists to make impossible.
    """
    elsewhere = _bundle_manifest(tmp_path / "elsewhere", version="9.9.9", name="some-other-plugin")

    items = release_adoption_items(
        project_root=elsewhere, repo="repo-under-test", bases=_positive_control_bases(tmp_path)
    )

    assert sorted(item.id for item in items) == [
        "hygiene:release-adoption:adopter-behind",
        "hygiene:release-adoption:adopter-current",
    ]


def test_positive_control_reports_a_current_adopter_as_current(tmp_path: Path) -> None:
    """THE POSITIVE CONTROL. A known-current adopter must be reported current.

    This assertion is what fails the build when the lane reports NO current
    adopter against a fixture that contains one — the exact silent failure a
    broken registry read or an unparsed manifest would otherwise produce.
    """
    items = _items(tmp_path, bases=_positive_control_bases(tmp_path))

    current = [item for item in items if "current" in item.summary and item.urgency == "low"]
    assert current, "the lane reported no current adopter against the positive control fixture"
    summary = _summary_for(items, adopter="adopter-current")
    assert f"resolves plugin build {_TIP_VERSION}" in summary
    assert "current" in summary
    assert "BEHIND" not in summary


def test_reports_an_adopter_whose_resolved_build_predates_the_release_tip(tmp_path: Path) -> None:
    items = _items(tmp_path, bases=_positive_control_bases(tmp_path))

    summary = _summary_for(items, adopter="adopter-behind")
    assert f"resolves plugin build {_STALE_VERSION}" in summary
    assert f"release tip {_TIP_VERSION}" in summary
    assert "BEHIND" in summary
    behind = [item for item in items if "BEHIND" in item.summary]
    assert [item.urgency for item in behind] == ["low"]
    command = behind[0].handoff.command
    assert "just adopt-orchestrator-build <clone> <build>" in command
    assert "Refresh the adopter" not in command
    assert "claude plugin update" not in command


def test_every_composed_item_clears_the_runtime_id_validator(tmp_path: Path) -> None:
    items = _items(tmp_path, bases=_positive_control_bases(tmp_path))

    assert items
    assert all(validate_attention_item_id(id=item.id) for item in items)
    assert all(item.kind == "hygiene" for item in items)


def test_recorded_results_are_verified_by_reading_the_persisted_envelope_back(
    tmp_path: Path,
) -> None:
    """Assert on the artifact's CONTENT, never on the fact that a write happened.

    A write that "succeeded" proves nothing about what it recorded, so each
    adopter's verdict is checked by re-reading the envelope from disk and
    inspecting the bytes a downstream consumer would receive.
    """
    envelope_path = tmp_path / "needs-attention.json"
    _ = envelope_path.write_text(
        render_json(attention=_items(tmp_path, bases=_positive_control_bases(tmp_path))),
        encoding="utf-8",
    )

    recorded = json.loads(envelope_path.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in recorded["attention"]}
    current = by_id["hygiene:release-adoption:adopter-current"]
    behind = by_id["hygiene:release-adoption:adopter-behind"]
    assert f"resolves plugin build {_TIP_VERSION}" in current["summary"]
    assert current["summary"].endswith("plugin.json.")
    assert current["urgency"] == "low"
    assert "BEHIND" not in current["summary"]
    assert f"resolves plugin build {_STALE_VERSION}" in behind["summary"]
    assert "BEHIND" in behind["summary"]
    assert behind["urgency"] == "low"
    assert behind["source_ref"]["path"] == str(tmp_path / "projects" / "adopter-behind")


def test_a_build_is_identified_by_its_manifest_not_by_its_directory_name(tmp_path: Path) -> None:
    """A cache directory named for one version may carry a manifest for another.

    Directories are keyed by commit AND by version and both shapes coexist, so
    a name-based match silently misreports. Here the STALE build sits in a
    directory named for the release-tip version; only manifest parsing catches
    it.
    """
    misleading = _flat_manifest(tmp_path / "builds" / _TIP_VERSION, version=_STALE_VERSION)
    bases = ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {
                    "projectPath": str(tmp_path / "projects" / "misleading-dir-name"),
                    "installPath": str(misleading),
                }
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )

    summary = _summary_for(_items(tmp_path, bases=bases), adopter="misleading-dir-name")
    assert f"resolves plugin build {_STALE_VERSION}" in summary
    assert "BEHIND" in summary


def test_an_unidentifiable_build_is_reported_behind_never_current(tmp_path: Path) -> None:
    bases = ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {
                    "projectPath": str(tmp_path / "projects" / "no-manifest"),
                    "installPath": str(tmp_path / "builds" / "empty"),
                },
                {"projectPath": str(tmp_path / "projects" / "no-install-path")},
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )

    items = _items(tmp_path, bases=bases)
    assert "unknown" in _summary_for(items, adopter="no-manifest")
    assert "BEHIND" in _summary_for(items, adopter="no-manifest")
    assert "BEHIND" in _summary_for(items, adopter="no-install-path")


def test_no_item_is_composed_when_every_adopter_resolves_the_release_tip(tmp_path: Path) -> None:
    build = _flat_manifest(tmp_path / "builds" / "current", version=_TIP_VERSION)
    bases = ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {
                    "projectPath": str(tmp_path / "projects" / "up-to-date"),
                    "installPath": str(build),
                }
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )

    assert _items(tmp_path, bases=bases) == []


def test_a_newer_adopter_build_than_the_release_tip_is_not_behind(tmp_path: Path) -> None:
    build = _flat_manifest(tmp_path / "builds" / "ahead", version="0.85.0")
    bases = ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {"projectPath": str(tmp_path / "projects" / "ahead"), "installPath": str(build)}
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )

    assert _items(tmp_path, bases=bases) == []


def test_no_item_is_composed_without_any_adopter_record(tmp_path: Path) -> None:
    bases = ReleaseAdoptionBases(
        install_record=tmp_path / "absent.json",
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )

    assert _items(tmp_path, bases=bases) == []


def test_an_unresolvable_release_tip_surfaces_instead_of_an_all_clear(tmp_path: Path) -> None:
    """A clone pinned off the release channel cannot answer the question.

    Reporting nothing here would manufacture an all-clear out of an unreadable
    instrument, and absence reads as resolution downstream.
    """
    build = _flat_manifest(tmp_path / "builds" / "some", version=_STALE_VERSION)
    bases = ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {"projectPath": str(tmp_path / "projects" / "adopter"), "installPath": str(build)}
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION, ref="master"),
    )

    items = _items(tmp_path, bases=bases)
    assert [item.id for item in items] == ["hygiene:release-adoption:unresolved-release-tip"]
    assert items[0].urgency == "high"
    assert "never an all-clear" in items[0].summary


def test_a_marketplace_clone_without_a_readable_manifest_yields_no_tip(tmp_path: Path) -> None:
    assert (
        release_tip_version(
            marketplace_record=_marketplace(tmp_path, version=None), plugin_name=_PLUGIN
        )
        is None
    )


def test_a_marketplace_record_without_an_install_location_yields_no_tip(tmp_path: Path) -> None:
    record = tmp_path / "known_marketplaces.json"
    _write_json(record, {_PLUGIN: {"source": {"ref": "release"}, "installLocation": ""}})

    assert release_tip_version(marketplace_record=record, plugin_name=_PLUGIN) is None


def test_a_marketplace_record_with_a_malformed_source_yields_no_tip(tmp_path: Path) -> None:
    record = tmp_path / "known_marketplaces.json"
    _write_json(record, {_PLUGIN: {"source": "not-an-object", "installLocation": "/x"}})

    assert release_tip_version(marketplace_record=record, plugin_name=_PLUGIN) is None


def test_read_build_version_prefers_the_build_root_manifest(tmp_path: Path) -> None:
    root = _bundle_manifest(tmp_path / "both", version=_STALE_VERSION)
    _ = _flat_manifest(root, version=_TIP_VERSION)

    assert read_build_version(install_path=root) == _TIP_VERSION
    assert read_build_version(install_path=tmp_path / "neither") is None


def test_a_manifest_whose_version_is_not_a_usable_string_is_unidentifiable(
    tmp_path: Path,
) -> None:
    """Neither a non-string version nor an empty one identifies a build."""
    typed_wrong = tmp_path / "typed-wrong"
    _write_json(typed_wrong / "plugin.json", {"name": _PLUGIN, "version": 84})
    blank = tmp_path / "blank"
    _write_json(blank / "plugin.json", {"name": _PLUGIN, "version": ""})

    assert read_build_version(install_path=typed_wrong) is None
    assert read_build_version(install_path=blank) is None


def test_records_for_other_plugins_and_malformed_entries_are_ignored(tmp_path: Path) -> None:
    record = tmp_path / "installed_plugins.json"
    _write_json(
        record,
        {
            "plugins": {
                "other-plugin@market": [{"projectPath": "/p", "installPath": "/i"}],
                f"{_PLUGIN}@market-a": "not-a-list",
                f"{_PLUGIN}@market-b": ["not-an-object", {"installPath": "/i"}],
            }
        },
    )
    bases = ReleaseAdoptionBases(
        install_record=record, marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION)
    )

    assert adopter_resolutions(bases=bases, plugin_name=_PLUGIN, tip_version=_TIP_VERSION) == ()


def test_an_unreadable_or_malformed_registry_yields_no_resolutions(tmp_path: Path) -> None:
    marketplace = _marketplace(tmp_path, version=_TIP_VERSION)
    undecodable = tmp_path / "undecodable.json"
    _ = undecodable.write_bytes(b"\xff\xfe not utf-8")
    not_json = tmp_path / "not-json.json"
    _ = not_json.write_text("{", encoding="utf-8")
    not_an_object = tmp_path / "not-an-object.json"
    _write_json(not_an_object, [1, 2, 3])
    plugins_not_an_object = tmp_path / "plugins-not-an-object.json"
    _write_json(plugins_not_an_object, {"plugins": "nope"})

    for record in (undecodable, not_json, not_an_object, plugins_not_an_object):
        bases = ReleaseAdoptionBases(install_record=record, marketplace_record=marketplace)
        assert adopter_resolutions(bases=bases, plugin_name=_PLUGIN, tip_version=None) == ()


def test_without_a_release_tip_an_identified_build_is_not_claimed_behind(tmp_path: Path) -> None:
    """`behind` is a comparison against a tip; with no tip there is no verdict.

    The unresolved-tip item is what the operator sees in that case, so this
    guards the resolution record itself against asserting a verdict it cannot
    justify — while an UNIDENTIFIABLE build stays behind either way.
    """
    identified = _flat_manifest(tmp_path / "builds" / "identified", version=_STALE_VERSION)
    bases = ReleaseAdoptionBases(
        install_record=_install_record(
            tmp_path,
            entries=[
                {
                    "projectPath": str(tmp_path / "projects" / "identified"),
                    "installPath": str(identified),
                },
                {
                    "projectPath": str(tmp_path / "projects" / "unidentifiable"),
                    "installPath": str(tmp_path / "builds" / "absent"),
                },
            ],
        ),
        marketplace_record=_marketplace(tmp_path, version=_TIP_VERSION),
    )

    resolutions = adopter_resolutions(bases=bases, plugin_name=_PLUGIN, tip_version=None)
    assert [(item.adopter, item.behind) for item in resolutions] == [
        ("identified", False),
        ("unidentifiable", True),
    ]
