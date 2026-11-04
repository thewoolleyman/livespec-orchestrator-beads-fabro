"""Coverage for the marker that says a judgement was recorded against an item.

The held-Definition-of-Done lane reads comments only for the items this marker
is on, so the marker's write and its listing read have to agree: an item the
sanctioned writer stamped must read back, and one it never stamped must not. The
unusable-record shapes are the ones a live tenant can hand back that the fake
tenant's own write surface never produces.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro import _store_dod_judgement_marker
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro._store_dod_judgement_marker import (
    DOD_JUDGEMENT_RECORDED_LABEL,
    mark_work_item_dod_judgement_recorded,
    read_dod_judged_work_item_ids,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(*, issue_id: str, labels: list[str]) -> None:
    _ = make_beads_client(config=_config()).create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=f"{issue_id} title",
            description="d",
            priority=2,
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
            labels=list(labels),
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )


def test_the_marker_label_is_the_persisted_spelling() -> None:
    assert DOD_JUDGEMENT_RECORDED_LABEL == "dod-judgement:recorded"


def test_only_the_stamped_ids_read_back_as_judged() -> None:
    _seed(issue_id="bd-judged", labels=["intake:triaged"])
    _seed(issue_id="bd-never", labels=["intake:triaged"])
    _seed(issue_id="bd-bare", labels=[])

    mark_work_item_dod_judgement_recorded(path=_config(), item_id="bd-judged")

    assert read_dod_judged_work_item_ids(path=_config()) == frozenset({"bd-judged"})


def test_stamping_an_item_that_already_carries_the_marker_changes_nothing() -> None:
    _seed(issue_id="bd-judged", labels=[])
    mark_work_item_dod_judgement_recorded(path=_config(), item_id="bd-judged")

    mark_work_item_dod_judgement_recorded(path=_config(), item_id="bd-judged")

    assert read_dod_judged_work_item_ids(path=_config()) == frozenset({"bd-judged"})


class _StubClient:
    def __init__(self, *, records: list[dict[str, object]]) -> None:
        self._records = records

    def list_issues(self) -> list[dict[str, object]]:
        return [dict(record) for record in self._records]


def test_an_unusable_record_contributes_nothing_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StubClient(
        records=[
            {"id": "bd-judged", "labels": [DOD_JUDGEMENT_RECORDED_LABEL]},
            {"id": 17, "labels": [DOD_JUDGEMENT_RECORDED_LABEL]},
            {"id": "bd-odd-labels", "labels": "not-a-list"},
            {"id": "bd-no-labels"},
            {"id": "bd-mixed-labels", "labels": [7, DOD_JUDGEMENT_RECORDED_LABEL]},
            {"id": "bd-other-label", "labels": ["intake:triaged"]},
        ]
    )
    monkeypatch.setattr(_store_dod_judgement_marker, "make_beads_client", lambda **_: stub)

    judged = read_dod_judged_work_item_ids(path=_config())

    assert judged == frozenset({"bd-judged", "bd-mixed-labels"})
