"""Witnesses for the delegated pre-commit aggregate configuration."""

from __future__ import annotations

import re
from pathlib import Path

from livespec_dev_tooling.config import load_delegated_pre_commit, load_gate_check_suite

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repository_config_opts_in_to_the_repaired_pre_commit_delegate() -> None:
    """The repository selects the released delegate and its staged-tree bootstrap."""
    assert load_delegated_pre_commit(repo_root=_REPO_ROOT) is True
    assert load_gate_check_suite(repo_root=_REPO_ROOT) == (
        "install-worktree-pack",
        "check-pre-commit",
    )

    config = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    tag_match = re.search(
        r'^livespec-dev-tooling = \{ git = "[^"]+", tag = "(v[^"]+)" \}$',
        config,
        flags=re.MULTILINE,
    )
    assert tag_match is not None
    tag = tag_match.group(1)
    assert tuple(int(part) for part in tag.removeprefix("v").split(".")) >= (1, 153, 0)

    lock = (_REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert lock.count(f"tag={tag}") == 2
