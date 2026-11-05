"""Focused tests for resolving the pull request that receives host proof."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_target import (
    reconciled_pr_selection,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_the_latest_complete_reconciliation_selection_wins(tmp_path: Path) -> None:
    """Malformed or unrelated journal rows cannot replace the selected pull request."""
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    _ = journal.parent.mkdir()
    records = (
        {
            "stage": "reconcile-pr-selected",
            "work_item_id": "bd-ib-host-record",
            "pr_number": 42,
            "merge_sha": "selected-merge",
        },
        {
            "stage": "reconcile-pr-selected",
            "work_item_id": "bd-ib-host-record",
            "pr_number": "not-a-number",
            "merge_sha": "invalid-selection",
        },
        {
            "stage": "reconcile-pr-selected",
            "work_item_id": "another-item",
            "pr_number": 10,
            "merge_sha": "another-merge",
        },
        {"stage": "other", "work_item_id": "bd-ib-host-record", "pr_number": 9},
    )
    _ = journal.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    selected = reconciled_pr_selection(
        repo=tmp_path,
        item=cast(WorkItem, SimpleNamespace(id="bd-ib-host-record")),
    )

    assert selected == 42


def test_the_red_fixture_can_model_a_second_title_match(tmp_path: Path) -> None:
    """The split-landing fixture emits both title-identifying merged pull requests."""
    red_module = runpy.run_path(
        str(Path(__file__).with_name("test_dispatcher_host_record_post.py"))
    )
    result = red_module["_Runner"](comments="[]", extra_title_match=True).run(
        argv=["gh", "pr", "list"], cwd=tmp_path, timeout_seconds=1.0
    )

    assert [pull_request["number"] for pull_request in json.loads(result.stdout)] == [42, 43]
