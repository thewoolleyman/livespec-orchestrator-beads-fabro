"""Tests for .claude-plugin/scripts/bin/_payload.py.

Unit coverage for the launcher's payload-retention decisions: which plugin
roots are harness-managed, that each invocation gets a payload no other
invocation shares, that no pre-existing tree is ever adopted as one, which
sources are refused as incomplete, that a failed or truncated copy cleans up
after itself, and how a release LABEL degrades when a present manifest cannot
be parsed.

The end-to-end counterparts can only be asked of real child processes:
`test_payload_retention_after_eviction.py` (what a live process sees after its
installation is deleted underneath it),
`test_payload_concurrent_release_isolation.py` (two concurrent invocations
keeping their own releases), and `test_payload_provisioning_refusal.py` (that a
refusal reaches the real CLI before any claim).
"""

import importlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE = "9.9.9"
_UNKNOWN_RELEASE = "unknown-release"
_HOLDER_PREFIX = "livespec-orchestrator-beads-fabro-payload-"

# Every member `_payload` requires of a usable payload, as the relative path
# its refusal names.
_REQUIRED = (
    "plugin.json",
    "scripts/bin/_bootstrap.py",
    "scripts/bin/_payload.py",
    "scripts/livespec_orchestrator_beads_fabro/__init__.py",
    "scripts/_vendor",
    ".fabro/workflows",
)


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path, manifest: str = f'{{"version": "{_RELEASE}"}}') -> Path:
    """A COMPLETE minimal installed plugin root, plus a stale cache to be dropped."""
    for relative in ("scripts/bin", "scripts/livespec_orchestrator_beads_fabro"):
        (root / relative).mkdir(parents=True)
    (root / "scripts" / "_vendor").mkdir(parents=True)
    (root / ".fabro" / "workflows").mkdir(parents=True)
    (root / "scripts" / "__pycache__").mkdir(parents=True)
    for relative in (
        "scripts/bin/_bootstrap.py",
        "scripts/bin/_payload.py",
        "scripts/livespec_orchestrator_beads_fabro/__init__.py",
        "scripts/__pycache__/stale.pyc",
    ):
        _ = (root / relative).write_text("", encoding="utf-8")
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
    """The one case that copies nothing: the operator's tree is left alone.

    It is also NOT validated. A checkout is not provisioned, so there is no
    provision to refuse, and holding a developer's working tree to a released
    payload's completeness contract would refuse mid-edit.
    """
    payload = _import_payload()
    _ = (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    source_root = tmp_path / ".claude-plugin"
    source_root.mkdir()
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
    source_root = _install(root=tmp_path / "cache" / "abc123")
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
    source_root = _install(root=tmp_path / "cache" / "abc123")
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
    foreign = _install(root=tmp_path / "foreign")
    _ = (foreign / "scripts" / "SMOKING-GUN").write_text("adopted", encoding="utf-8")
    decoy = temp_root / f"{_HOLDER_PREFIX}{_RELEASE}"
    decoy.mkdir()
    (decoy / "payload").symlink_to(foreign, target_is_directory=True)

    source_root = _install(root=tmp_path / "cache" / "abc123")
    retained = payload.retain_payload(source_root=source_root)
    assert retained.root.parent != decoy
    assert not retained.root.is_symlink()
    assert not (
        retained.scripts_root / "SMOKING-GUN"
    ).exists(), "the launcher adopted a pre-existing tree as its executable payload"


@pytest.mark.parametrize("absent", _REQUIRED)
def test_a_source_missing_any_required_member_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, absent: str
) -> None:
    """Each required member, removed on its own, must be named in the refusal."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    target = source_root.joinpath(*absent.split("/"))
    shutil.rmtree(target) if target.is_dir() else target.unlink()

    refusal = payload.retain_payload(source_root=source_root)
    assert isinstance(refusal, payload.PayloadRefusal)
    assert absent in refusal.message
    assert str(source_root) in refusal.message
    assert "Nothing was claimed" in refusal.message
    assert list(temp_root.iterdir()) == [], "a refused provision created a holder anyway"


def test_a_copy_that_fails_is_refused_and_leaves_no_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dangling symlink makes the real copy fail part-way; the holder must go."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    (source_root / "scripts" / "dangling-link").symlink_to(tmp_path / "nothing-here")

    refusal = payload.retain_payload(source_root=source_root)
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "copying the installed release" in refusal.message
    assert str(source_root) in refusal.message
    assert list(temp_root.iterdir()) == [], "the failed copy left its holder behind"


def test_a_copy_that_silently_truncates_is_refused_and_leaves_no_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A copy can SUCCEED and still be incomplete — the eviction-mid-provision case.

    The source passed its own completeness check moments earlier, so a copy
    that lands short means the source changed underneath it. `copytree` is
    replaced with one that reports success while writing almost nothing, which
    is the only way to reach that arm deterministically.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")

    def _truncating_copytree(_source: Path, destination: Path, **_kwargs: object) -> Path:
        destination.mkdir(parents=True)
        _ = (destination / "plugin.json").write_text("{}", encoding="utf-8")
        return destination

    monkeypatch.setattr(payload.shutil, "copytree", _truncating_copytree)
    refusal = payload.retain_payload(source_root=source_root)
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "copy at" in refusal.message
    assert "scripts/_vendor" in refusal.message
    assert list(temp_root.iterdir()) == [], "the truncated copy left its holder behind"


@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param("{not json", id="malformed"),
        pytest.param("[]", id="not-an-object"),
        pytest.param('{"version": 7}', id="version-not-a-string"),
        pytest.param('{"version": "   "}', id="version-blank"),
    ],
)
def test_an_unparseable_release_label_still_yields_a_retained_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, manifest: str
) -> None:
    """A manifest that is PRESENT but odd is cosmetic — it only labels the holder."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123", manifest=manifest)
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is True
    assert retained.root.parent.name.startswith(f"{_HOLDER_PREFIX}{_UNKNOWN_RELEASE}-")
    assert retained.vendor_root.is_dir()


def test_an_unreadable_release_manifest_still_yields_a_retained_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Present but unreadable is cosmetic too — the read error must not refuse."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    # A DIRECTORY named plugin.json exists, so the completeness check passes
    # while the text read raises OSError.
    (source_root / "plugin.json").unlink()
    (source_root / "plugin.json").mkdir()
    retained = payload.retain_payload(source_root=source_root)
    assert retained.retained is True
    assert retained.root.parent.name.startswith(f"{_HOLDER_PREFIX}{_UNKNOWN_RELEASE}-")
