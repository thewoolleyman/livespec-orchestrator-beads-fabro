"""Tests for .claude-plugin/scripts/bin/_payload.py.

Unit coverage for the launcher's payload-retention decisions: which plugin
roots are harness-managed, that each invocation gets a payload no other
invocation shares, that no pre-existing tree is ever adopted as one, and how a
release label degrades when the manifest cannot be read.

The end-to-end counterparts — what a LIVE process sees after its installation
is deleted underneath it, and whether two concurrent invocations keep their own
releases — are `test_payload_retention_after_eviction.py` and
`test_payload_concurrent_release_isolation.py`, which can only be asked of
real child processes.
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
_HOLDER_PREFIX = "livespec-orchestrator-beads-fabro-payload-"


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


def _private_tempdir(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point `tempfile` at a per-test directory so holders are observable."""
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    return temp_root


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


def test_an_installed_plugin_root_is_copied_into_a_private_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=f'{{"version": "{_RELEASE}"}}'
    )
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is True
    assert retained.root.parent.parent == temp_root
    # The release LABELS the holder for a human reading /tmp; it is not identity.
    assert retained.root.parent.name.startswith(f"{_HOLDER_PREFIX}{_RELEASE}-")
    assert (retained.scripts_root / "livespec_orchestrator_beads_fabro").is_dir()
    assert retained.vendor_root.is_dir()
    assert not (
        retained.scripts_root / "__pycache__"
    ).exists(), "byte-compiled caches are reproducible and must not be carried into the payload"


def test_each_invocation_gets_a_payload_no_other_invocation_shares(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two retentions of the SAME release must not resolve the same tree."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=f'{{"version": "{_RELEASE}"}}'
    )
    first = payload.retain_payload(source_root=source_root)
    second = payload.retain_payload(source_root=source_root)
    assert first.root != second.root
    # A write into one payload must be invisible to the other — the property a
    # shared release-keyed directory could not provide.
    _ = (first.root / "witness").write_text("first", encoding="utf-8")
    assert not (second.root / "witness").exists()


def test_a_pre_existing_tree_at_a_guessable_path_is_never_adopted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Adoption is structurally impossible: no existing path is consulted.

    The decoys are the ones a guessable, release-keyed payload path invited —
    a complete-looking foreign tree, reached through a symlink, planted under
    the exact prefix the launcher labels its holders with. Neither the foreign
    code nor the symlink may end up in the executable payload.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    foreign = _install(root=tmp_path / "foreign", manifest=f'{{"version": "{_RELEASE}"}}')
    _ = (foreign / "scripts" / "SMOKING-GUN").write_text("adopted", encoding="utf-8")
    decoy = temp_root / f"{_HOLDER_PREFIX}{_RELEASE}"
    decoy.mkdir()
    (decoy / "payload").symlink_to(foreign, target_is_directory=True)

    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=f'{{"version": "{_RELEASE}"}}'
    )
    retained = payload.retain_payload(source_root=source_root)
    assert retained.root.parent != decoy
    assert not retained.root.is_symlink()
    assert not (
        retained.scripts_root / "SMOKING-GUN"
    ).exists(), "the launcher adopted a pre-existing tree as its executable payload"


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
def test_an_unreadable_release_label_still_yields_a_retained_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, manifest: str | None
) -> None:
    """A cosmetic manifest fault must not turn into a dead launcher."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123", manifest=manifest)
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is True
    assert retained.root.parent.name.startswith(f"{_HOLDER_PREFIX}{_UNKNOWN_RELEASE}-")
    assert retained.vendor_root.is_dir()
