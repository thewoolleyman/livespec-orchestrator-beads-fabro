"""Tests for the Spec Reader adapter."""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.spec_reader import (
    current_specification_version,
    diff_specification_versions,
    read_current_specification,
    read_specification_history,
)
from livespec_runtime.spec_stated import judge
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io


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


def test_read_current_specification_includes_a_declared_inherited_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A constraint's inherited specification remains citable by a verdict."""
    spec_root = tmp_path / "repository" / "SPECIFICATION"
    _seed_spec(spec_root=spec_root)
    inherited_key = "livespec/SPECIFICATION/non-functional-requirements.md"
    _ = (spec_root / "constraints.md").write_text(
        "Every constraint in `livespec/SPECIFICATION/non-functional-requirements.md` "
        "applies to this plugin without restatement.\n",
        encoding="utf-8",
    )
    sibling_root = tmp_path / "siblings"
    inherited = sibling_root / inherited_key
    inherited.parent.mkdir(parents=True)
    _ = inherited.write_text(
        "## Inherited credential boundary\n\nCredential helpers remain private to hooks.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIVESPEC_SIBLING_CLONES_ROOT", str(sibling_root))

    snapshot = read_current_specification(spec_root=spec_root)
    verdict = judge(
        spec_tree=snapshot.files,
        statement="Credential helpers remain private to hooks.",
        run_model=lambda _prompt: (
            '{"kind":"stated","stated_by":["## Inherited credential boundary"],'
            '"generalization_target":null,"rationale":""}'
        ),
    )

    assert inherited_key in snapshot.files
    assert snapshot.files[inherited_key] == inherited.read_text(encoding="utf-8")
    assert is_successful(verdict)


def test_read_specification_history_happy_path(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=3, content="# v3 spec\n")
    snapshot = unsafe_perform_io(
        read_specification_history(spec_root=spec_root, version=3).unwrap()
    )
    assert snapshot.version == 3
    assert snapshot.files == {"spec.md": "# v3 spec\n"}


def test_read_specification_history_missing_version_is_a_failure(tmp_path: Path) -> None:
    """An absent vNNN/ directory is an EXPECTED failure, so it rides the failure track."""
    spec_root = tmp_path / "SPECIFICATION"
    spec_root.mkdir(parents=True)
    result = read_specification_history(spec_root=spec_root, version=42)
    assert not is_successful(result)
    error = unsafe_perform_io(result.failure())
    assert error.version == 42


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


def test_diff_specification_versions_absent_version_a_is_a_failure(tmp_path: Path) -> None:
    """An absent FIRST version rides the failure track instead of raising."""
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=2, content="# v2 spec\n")
    result = diff_specification_versions(spec_root=spec_root, version_a=41, version_b=2)
    assert not is_successful(result)
    assert unsafe_perform_io(result.failure()).version == 41


def test_diff_specification_versions_absent_version_b_is_a_failure(tmp_path: Path) -> None:
    """An absent SECOND version rides the failure track too.

    Distinct from the version_a case: version_a resolves first, so this
    covers the branch that only trips once the first read has succeeded.
    """
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=1, content="# v1 spec\n")
    result = diff_specification_versions(spec_root=spec_root, version_a=1, version_b=43)
    assert not is_successful(result)
    assert unsafe_perform_io(result.failure()).version == 43


def test_diff_specification_versions_identical_files_excluded(
    tmp_path: Path,
) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=1, content="# identical\n")
    _seed_history(spec_root=spec_root, version=2, content="# identical\n")
    diff = unsafe_perform_io(
        diff_specification_versions(spec_root=spec_root, version_a=1, version_b=2).unwrap()
    )
    assert diff.per_file == {}
    assert diff.version_a == 1
    assert diff.version_b == 2


def test_diff_specification_versions_modified_file(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _seed_history(spec_root=spec_root, version=1, content="line a\n")
    _seed_history(spec_root=spec_root, version=2, content="line b\n")
    diff = unsafe_perform_io(
        diff_specification_versions(spec_root=spec_root, version_a=1, version_b=2).unwrap()
    )
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
    diff = unsafe_perform_io(
        diff_specification_versions(spec_root=spec_root, version_a=1, version_b=2).unwrap()
    )
    assert "new-file.md" in diff.per_file
    assert diff.per_file["new-file.md"].added_lines == 1
    assert diff.per_file["new-file.md"].removed_lines == 0
