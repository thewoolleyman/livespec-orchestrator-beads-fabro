"""Paired coverage for local type wrappers and runtime re-exports."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.types import FileDiff, SpecDiff, StoreConfig, WorkItem
from livespec_runtime.work_items.types import WorkItem as RuntimeWorkItem


def test_store_config_work_items_path_returns_descriptor() -> None:
    config = StoreConfig(
        tenant="tenant",
        prefix="bd",
        server_user="tenant",
        database="tenant",
        bd_path="/usr/local/bin/bd",
        repo_root=Path("/repo"),
    )

    assert config.work_items_path is config


def test_spec_diff_and_runtime_work_item_reexport() -> None:
    file_diff = FileDiff(
        path="SPECIFICATION/contracts.md", added_lines=2, removed_lines=1, unified_diff="@@"
    )
    diff = SpecDiff(version_a=1, version_b=2, per_file={file_diff.path: file_diff})

    assert diff.per_file["SPECIFICATION/contracts.md"] is file_diff
    assert WorkItem is RuntimeWorkItem
