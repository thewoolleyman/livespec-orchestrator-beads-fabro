"""The gh-refresh support files are copied one by one, and the overlay is clock-independent.

The support bundle used to ride the overlay as a gzip tarball whose header clock
had to be pinned. It is now a set of helper programs the helper-fetch setup step
copies from the installed build's checkout, each file its own digest-verified
helper, so what is asserted is the set of files and that the overlay carrying
the wrapper step still renders identically when only the wall clock moves.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    github_auth_support_relpaths,
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
    (root / "_vendor/returns/__pycache__").mkdir()
    (root / "_vendor/returns/__pycache__/x.cpython-313.pyc").write_bytes(b"\0")


def test_the_support_files_are_every_python_file_under_the_bundle_paths(*, tmp_path: Path) -> None:
    """Directories contribute their `.py` files, sorted; nothing else rides along."""
    _support_tree(root=tmp_path)
    relpaths = github_auth_support_relpaths(scripts_root=tmp_path)
    assert [path.as_posix() for path in relpaths] == list(_SUPPORT_FILES)


def test_no_work_item_overlay_is_byte_identical_across_seconds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force the wrapper step into the overlay, independent of ambient secrets."""
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
