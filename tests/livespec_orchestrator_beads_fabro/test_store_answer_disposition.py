"""Coverage for the narrow `answer:` label read.

The per-item answer-disposition override is a label, and
`store._record_to_work_item` decodes labels into the named fields the shared
`WorkItem` model declares — a model this repository does not own and cannot
extend. So the attention snapshot reads the marker here, from the raw record,
and this file pins the two properties that read has to hold: it returns the
labels RAW (resolution belongs to the policy layer, not to a store reader), and
it is fail-soft over the record shapes a live tenant can hand back.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro import _store_answer_disposition
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    ANSWER_DISPOSITION_LABEL_PREFIX,
    read_answer_disposition_labels,
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
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=f"{issue_id} title",
            description="d",
            priority=2,
            assignee=None,
            created_at="2026-09-07T00:00:00Z",
            labels=list(labels),
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )


def test_only_answer_prefixed_labels_read_back_and_they_read_back_raw() -> None:
    """Unrelated labels are dropped, and a `consensus` value survives unjudged.

    The raw-ness matters: a reader that pre-resolved `consensus` to `human` here
    would make the asymmetry unobservable to the policy layer that owns it.
    """
    _seed(
        issue_id="bd-lowered",
        labels=[f"{ANSWER_DISPOSITION_LABEL_PREFIX}human", "intake:triaged"],
    )
    _seed(issue_id="bd-raised", labels=[f"{ANSWER_DISPOSITION_LABEL_PREFIX}consensus"])
    _seed(issue_id="bd-bare", labels=["merge-hold:on"])

    labels = read_answer_disposition_labels(path=_config())

    assert labels == {
        "bd-lowered": ("answer:human",),
        "bd-raised": ("answer:consensus",),
    }


class _StubClient:
    """A read-only stand-in returning a fixed raw record set.

    Mirrors `test_store_merge_hold`'s stub, and for the same reason: the shapes
    below — a non-string id, labels that are not a list, a label list holding a
    non-string — are ones the fake tenant's own write surface never produces,
    while a live tenant read through a mismatched or truncated record can.
    """

    def __init__(self, *, records: list[dict[str, object]]) -> None:
        self._records = records

    def list_issues(self) -> list[dict[str, object]]:
        return [dict(record) for record in self._records]


def test_an_unusable_record_contributes_nothing_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-soft over every unusable shape, while the usable rows still read."""
    label = f"{ANSWER_DISPOSITION_LABEL_PREFIX}human"
    stub = _StubClient(
        records=[
            {"id": "bd-labelled", "labels": [label]},
            {"id": 17, "labels": [label]},
            {"id": "bd-odd-labels", "labels": "not-a-list"},
            {"id": "bd-mixed-labels", "labels": [7, label]},
        ]
    )
    monkeypatch.setattr(_store_answer_disposition, "make_beads_client", lambda **_: stub)

    assert read_answer_disposition_labels(path=_config()) == {
        "bd-labelled": (label,),
        "bd-mixed-labels": (label,),
    }
