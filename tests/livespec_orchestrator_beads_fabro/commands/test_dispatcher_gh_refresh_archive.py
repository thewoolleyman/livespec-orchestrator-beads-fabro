"""The auth bundle and its overlay must not depend on the gzip header clock."""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    github_auth_support_archive_b64,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_SUPPORT_FILES = {
    "_vendor/livespec_runtime/__init__.py": b'"""Runtime package."""\n',
    "_vendor/livespec_runtime/github_auth/__init__.py": b"# Auth package\n",
    "_vendor/livespec_runtime/github_auth/provider.py": b"# Token provider\n",
    "_vendor/returns/__init__.py": b"# Result rails\n",
    "_vendor/returns/nested/result.py": b"# Nested support module\n",
    "_vendor/typing_extensions.py": b"# Typing support\n",
}


def _support_tree(*, root: Path) -> None:
    for name, content in _SUPPORT_FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "_vendor/returns/ignored.txt").write_text("not Python", encoding="utf-8")


def test_support_archive_is_byte_identical_across_seconds(*, tmp_path: Path) -> None:
    """Move the clock explicitly so the regression cannot pass by lucky timing."""
    _support_tree(root=tmp_path)
    with patch("time.time", return_value=1_800_000_000):
        first = github_auth_support_archive_b64(scripts_root=tmp_path)
    with patch("time.time", return_value=1_800_000_002):
        second = github_auth_support_archive_b64(scripts_root=tmp_path)

    identical = first == second
    assert identical, "output changed when only the wall clock advanced"


def test_no_work_item_overlay_is_byte_identical_across_seconds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force the real auth bundle into the overlay, independent of ambient secrets."""
    monkeypatch.setenv("GITHUB_APP_ID", "archive-test-app")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "archive-test-placeholder")
    workflow = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "sandbox"\n'
    with patch("time.time", return_value=1_800_000_000):
        first = render_run_config_overlay(
            committed_text=workflow,
            workflow_dir=tmp_path,
            token="",
            github_token="",
            siblings=None,
            publication_metadata=None,
        )
    with patch("time.time", return_value=1_800_000_002):
        second = render_run_config_overlay(
            committed_text=workflow,
            workflow_dir=tmp_path,
            token="",
            github_token="",
            siblings=None,
        )

    assert first is not None
    assert "livespec-refreshing-gh-wrapper" in first
    identical = first == second
    assert identical, "output changed when only the wall clock advanced"


def test_support_archive_extracts_the_same_paths_and_contents(*, tmp_path: Path) -> None:
    """Exercise the sandbox's tar.gz extraction with files and nested packages."""
    root = tmp_path / "scripts"
    _support_tree(root=root)
    payload = base64.b64decode(github_auth_support_archive_b64(scripts_root=root))
    destination = tmp_path / "sandbox"
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        assert archive.getnames() == list(_SUPPORT_FILES)
        for member in archive.getmembers():
            assert member.mtime == (root / member.name).stat().st_mtime
        archive.extractall(destination, filter="data")

    extracted = {
        str(path.relative_to(destination)): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert extracted == _SUPPORT_FILES
