"""The journal comparison that prevents a stale preserved tree from winning."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_is_later,
)


class _Runner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if "refs/livespec/preserved-publish/item/tree" in argv:
            return CommandResult(
                exit_code=0,
                stdout="tree\trefs/livespec/preserved-publish/item/tree\n",
                stderr="",
            )
        return CommandResult(exit_code=128, stdout="", stderr="origin unavailable")


@pytest.mark.parametrize(
    ("records", "preserved_run_id", "published_head", "expected"),
    [
        (
            (
                {"run_id": "older"},
                {"run_id": "newer", "published_head": "head"},
            ),
            "older",
            "head",
            True,
        ),
        (
            ({"run_id": "same", "published_head": "head"},),
            "same",
            "head",
            False,
        ),
        (({"run_id": "older"},), "older", "head", False),
        (({"published_head": "head"},), "older", "head", False),
        (({"run_id": "other", "published_head": "head"},), "older", "head", False),
    ],
)
def test_published_head_is_later_only_for_a_proven_later_journal_run(
    *,
    records: tuple[dict[str, object], ...],
    preserved_run_id: str,
    published_head: str,
    expected: bool,
) -> None:
    assert (
        published_head_is_later(
            records=records,
            preserved_run_id=preserved_run_id,
            published_head=published_head,
        )
        is expected
    )


def test_an_unreadable_competing_publish_branch_keeps_the_verified_tree() -> None:
    seed = verified_preserved_seed(
        runner=_Runner(),
        repo=Path("/repo"),
        work_item_id="item",
        earlier_run_ids=(),
        journal_records=(
            {
                "stage": "preserved-tree",
                "work_item_id": "item",
                "run_id": "older",
                "base_commit": "base",
                "preservation_ref": "refs/livespec/preserved-publish/item/tree",
            },
            {"work_item_id": "item", "run_id": "newer", "published_head": "head"},
        ),
    )
    assert seed is not None
    assert seed.commit_sha == "base"
