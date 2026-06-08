"""Tests for the Spec Reader adapter."""

from pathlib import Path

import pytest
from livespec_impl_beads.errors import SpecVersionNotFoundError
from livespec_impl_beads.spec_reader import (
    current_specification_version,
    diff_specification_versions,
    read_current_specification,
    read_specification_history,
)


def _seed_spec(*, spec_root: Path) -> None:
    spec_root.mkdir(parents=True, exist_ok=True)
    _ = (spec_root / "spec.md").write_text("# spec.md\nintent\n", encoding="utf-8")
    _ = (spec_root / "contracts.md").write_text("# contracts.md\nwire surface\n", encoding="utf-8")
    proposed = spec_root / "proposed_changes"
    proposed.mkdir(exist_ok=True)
    _ = (proposed / "pending.md").write_text("# pending proposal\n", encoding="utf-8")


def _seed_history(*, spec_root: Path, version: int, content: str) -> None:
    version_dir = spec_root / "history" / f"v{version:03d}"
    version_dir.mkdir(parents=True, exist_ok=True)
    _ = (version_dir / "spec.md").write_text(content, encoding="utf-8")


def test_read_current_specification_excludes_proposed_changes(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_spec(spec_root=spec_root)
    snapshot = read_current_specification(spec_root=spec_root)
    assert "spec.md" in snapshot.files
    assert "contracts.md" in snapshot.files
    assert not any("proposed_changes" in name for name in snapshot.files)


def test_read_current_specification_excludes_history(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_spec(spec_root=spec_root)
    _seed_history(spec_root=spec_root, version=1, content="# v1 spec\n")
    snapshot = read_current_specification(spec_root=spec_root)
    assert not any("history" in name for name in snapshot.files)
    assert snapshot.version == 1


def test_read_current_specification_returns_zero_when_no_history(
    tmp_path: Path,
) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_spec(spec_root=spec_root)
    snapshot = read_current_specification(spec_root=spec_root)
    assert snapshot.version == 0


def test_read_specification_history_happy_path(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=3, content="# v3 spec\n")
    snapshot = read_specification_history(spec_root=spec_root, version=3)
    assert snapshot.version == 3
    assert snapshot.files == {"spec.md": "# v3 spec\n"}


def test_read_specification_history_missing_version_raises(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    spec_root.mkdir(parents=True)
    with pytest.raises(SpecVersionNotFoundError) as excinfo:
        _ = read_specification_history(spec_root=spec_root, version=42)
    assert excinfo.value.version == 42


def test_current_specification_version_no_history_dir(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    spec_root.mkdir()
    assert current_specification_version(spec_root=spec_root) == 0


def test_current_specification_version_picks_max(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    for version in (1, 5, 3):
        _seed_history(spec_root=spec_root, version=version, content=f"# v{version}\n")
    assert current_specification_version(spec_root=spec_root) == 5


def test_current_specification_version_skips_non_version_dirs(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    history = spec_root / "history"
    history.mkdir(parents=True)
    (history / "not-a-version").mkdir()
    (history / "README.md").write_text("readme", encoding="utf-8")
    _seed_history(spec_root=spec_root, version=2, content="# v2\n")
    assert current_specification_version(spec_root=spec_root) == 2


def test_current_specification_version_no_versions(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    history = spec_root / "history"
    history.mkdir(parents=True)
    (history / "not-a-version").mkdir()
    assert current_specification_version(spec_root=spec_root) == 0


def test_diff_specification_versions_identical_files_excluded(
    tmp_path: Path,
) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=1, content="# identical\n")
    _seed_history(spec_root=spec_root, version=2, content="# identical\n")
    diff = diff_specification_versions(spec_root=spec_root, version_a=1, version_b=2)
    assert diff.per_file == {}
    assert diff.version_a == 1
    assert diff.version_b == 2


def test_diff_specification_versions_modified_file(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=1, content="line a\n")
    _seed_history(spec_root=spec_root, version=2, content="line b\n")
    diff = diff_specification_versions(spec_root=spec_root, version_a=1, version_b=2)
    file_diff = diff.per_file["spec.md"]
    assert file_diff.added_lines == 1
    assert file_diff.removed_lines == 1
    assert "line a" in file_diff.unified_diff
    assert "line b" in file_diff.unified_diff


def test_diff_specification_versions_added_file(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=1, content="# v1\n")
    v2_dir = spec_root / "history" / "v002"
    v2_dir.mkdir(parents=True)
    _ = (v2_dir / "spec.md").write_text("# v1\n", encoding="utf-8")
    _ = (v2_dir / "new-file.md").write_text("new\n", encoding="utf-8")
    diff = diff_specification_versions(spec_root=spec_root, version_a=1, version_b=2)
    assert "new-file.md" in diff.per_file
    assert diff.per_file["new-file.md"].added_lines == 1
    assert diff.per_file["new-file.md"].removed_lines == 0
