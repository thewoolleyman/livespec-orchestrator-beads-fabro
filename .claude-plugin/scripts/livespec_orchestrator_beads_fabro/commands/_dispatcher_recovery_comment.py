"""Durable preserved-tree comment reads and seed verification."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
    preserved_tree_comment,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.errors import ConnectionPrefixMissingError
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["comment_seed", "comment_tree_for_item"]


def comment_tree_for_item(*, repo: Path, item: WorkItem) -> tuple[str, str, str] | None:
    try:
        comments = read_work_item_comments(path=store_config(repo=repo), work_item_id=item.id)
    except ConnectionPrefixMissingError:
        return None
    return preserved_tree_comment(
        comments=tuple(one.text for one in comments), work_item_id=item.id
    )


def comment_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    item: WorkItem,
    journal_records: tuple[dict[str, object], ...],
    comment_tree: tuple[str, str, str],
) -> RecoverySeed | PreservedWorkUnobservable | PreservedWorkAbsent:
    return verified_preserved_seed(
        runner=runner,
        repo=repo,
        work_item_id=item.id,
        earlier_run_ids=(comment_tree[2],),
        journal_records=journal_records,
        comment_tree=comment_tree,
    )
