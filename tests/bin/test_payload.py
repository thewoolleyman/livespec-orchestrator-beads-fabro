"""Tests for .claude-plugin/scripts/bin/_payload.py.

Unit coverage for the launcher's payload-retention decisions: which plugin
roots are harness-managed, how a release identity is read (and every way that
read can degrade), that a published payload is reused rather than re-copied,
and that a copy which loses the publish race discards its own staging instead
of leaving two trees behind.

The end-to-end counterpart — what a LIVE process sees after its installation
is deleted underneath it — is
`test_payload_retention_after_eviction.py`, which can only be asked of a real
child process.
"""

import importlib
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE = "9.9.9"
_UNKNOWN_RELEASE = "unknown-release"


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path, manifest: str | None = None) -> Path:
    """A minimal installed plugin root: a manifest plus a scripts tree."""
    (root / "scripts" / "livespec_orchestrator_beads_fabro").mkdir(parents=True)
    (root / "scripts" / "_vendor").mkdir(parents=True)
    (root / "scripts" / "__pycache__").mkdir(parents=True)
    _ = (root / "scripts" / "__pycache__" / "stale.pyc").write_text("x", encoding="utf-8")
    if manifest is not None:
        _ = (root / "plugin.json").write_text(manifest, encoding="utf-8")
    return root


def test_a_plugin_root_beside_its_source_repository_is_not_harness_managed(
    tmp_path: Path,
) -> None:
    payload = _import_payload()
    _ = (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert payload.harness_managed(source_root=tmp_path / ".claude-plugin") is False


def test_a_plugin_root_beside_a_justfile_alone_is_not_harness_managed(
    tmp_path: Path,
) -> None:
    payload = _import_payload()
    _ = (tmp_path / "justfile").write_text("default:\n", encoding="utf-8")
    assert payload.harness_managed(source_root=tmp_path / ".claude-plugin") is False


def test_a_plugin_root_with_no_repository_above_it_is_harness_managed(
    tmp_path: Path,
) -> None:
    payload = _import_payload()
    assert payload.harness_managed(source_root=tmp_path / "cache-root") is True


def test_a_checkout_plugin_root_is_its_own_payload(tmp_path: Path) -> None:
    """The one case that copies nothing: the operator's tree is left alone."""
    payload = _import_payload()
    _ = (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    source_root = _install(root=tmp_path / ".claude-plugin")
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is False
    assert retained.root == source_root
    assert retained.scripts_root == source_root / "scripts"
    assert retained.vendor_root == source_root / "scripts" / "_vendor"


def test_an_installed_plugin_root_is_copied_aside_and_keyed_by_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _import_payload()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=f'{{"version": "{_RELEASE}"}}'
    )
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is True
    assert retained.root.name.endswith(_RELEASE)
    assert retained.root.parent == tmp_path / "tmp"
    assert (retained.scripts_root / "livespec_orchestrator_beads_fabro").is_dir()
    assert retained.vendor_root.is_dir()
    assert not (
        retained.scripts_root / "__pycache__"
    ).exists(), "byte-compiled caches are reproducible and must not be carried into the payload"
    # No staging holder is left behind once the payload is published.
    assert sorted(entry.name for entry in (tmp_path / "tmp").iterdir()) == [retained.root.name]


def test_an_already_published_payload_is_reused_rather_than_recopied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _import_payload()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=f'{{"version": "{_RELEASE}"}}'
    )
    first = payload.retain_payload(source_root=source_root)
    _ = (first.root / "witness").write_text("first", encoding="utf-8")
    second = payload.retain_payload(source_root=source_root)
    assert second.root == first.root
    assert (second.root / "witness").read_text(encoding="utf-8") == "first"


def test_losing_the_publish_race_discards_the_staging_and_takes_the_winner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A rename that cannot land must leave exactly one payload, not two trees."""
    payload = _import_payload()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=f'{{"version": "{_RELEASE}"}}'
    )
    # A rename onto a NON-EMPTY directory is refused by the kernel, which is
    # exactly the race's own failure: the winner has already published a full
    # tree under this name. No monkeypatching — the real `rename` says no.
    published = tmp_path / "published"
    published.mkdir()
    _ = (published / "winner").write_text("already here", encoding="utf-8")

    root = payload._published(source_root=source_root, root=published)  # noqa: SLF001
    assert root == published
    assert (published / "winner").read_text(encoding="utf-8") == "already here"
    assert (
        list((tmp_path / "tmp").iterdir()) == []
    ), "the losing copy left its staging holder behind"


@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param(None, id="absent"),
        pytest.param("{not json", id="malformed"),
        pytest.param("[]", id="not-an-object"),
        pytest.param('{"version": 7}', id="version-not-a-string"),
        pytest.param('{"version": "   "}', id="version-blank"),
    ],
)
def test_an_unreadable_release_identity_still_yields_a_retained_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, manifest: str | None
) -> None:
    """A cosmetic manifest fault must not turn into a dead launcher."""
    payload = _import_payload()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    source_root = _install(root=tmp_path / "cache" / "abc123", manifest=manifest)
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is True
    assert retained.root.name.endswith(_UNKNOWN_RELEASE)
    assert retained.vendor_root.is_dir()
