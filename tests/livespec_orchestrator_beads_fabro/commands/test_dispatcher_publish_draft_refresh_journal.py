"""The publish-base refresh is projected into the dispatch journal."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Protocol, cast


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _JournalRefresh(Protocol):
    def __call__(
        self,
        *,
        journal: _Journal,
        work_item_id: str,
        text: str,
    ) -> None: ...


def test_publish_draft_refresh_journal_names_branch_and_both_bases() -> None:
    journal_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal"
    )
    assert hasattr(journal_module, "journal_publish_draft_refresh")
    journal_refresh = cast("_JournalRefresh", journal_module.journal_publish_draft_refresh)
    journal = _Journal()
    before = "1" * 40
    after = "2" * 40

    journal_refresh(journal=journal, work_item_id="bd-ib-qustjx", text="unrelated output")
    journal_refresh(
        journal=journal,
        work_item_id="bd-ib-qustjx",
        text=(
            "stage output\n"
            "LIVESPEC_PUBLISH_DRAFT_REFRESH: "
            "publish_branch=feat/bd-ib-qustjx "
            f"base_before={before} base_after={after}\n"
        ),
    )

    assert journal.records == [
        {
            "work_item_id": "bd-ib-qustjx",
            "stage": "publish-draft-refresh",
            "publish_branch": "feat/bd-ib-qustjx",
            "base_before": before,
            "base_after": after,
        }
    ]
