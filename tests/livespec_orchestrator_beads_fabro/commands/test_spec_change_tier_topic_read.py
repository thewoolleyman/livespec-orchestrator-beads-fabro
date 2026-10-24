"""The two degraded ledger shapes the linked-topic read must survive.

The topic an item CARRIES is read off its beads labels through the connection
the caller already holds. Both failure arms answer "this item links no topic",
which is the same absence an unlabelled item presents, and neither may raise:
the read sits inside the intake router and inside the pre-dispatch wall.

THE SPARSE SHAPE IS NOT HYPOTHETICAL. Beads records are `omitempty`-sparse, so
`labels` is ABSENT from a record carrying none rather than present and empty —
`AGENTS.md` measures it on 280 of 523 records of a live tenant. A reader
indexing the key would raise on the ordinary case.

THE CONTROL IS THE SAME CALL OVER A WELL-FORMED RECORD. "No topic was read" is
satisfied by a reader that never reads one, so each case is paired with a
record whose label IS read and reaches the classification.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _spec_change_tier_gate
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SpecChangeTierVerdict
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    spec_change_tier_hold,
)
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_TOPIC = "spec-stated-judgement-and-spec-change-tier"
_ITEM = "bd-ib-57ss2n"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="feature",
        status="ready",
        title="The spec-change tier is decided by the spec-stated judgement",
        description="## Definition of Done\n\n- The tier is decided.\n\nReferences: ## Other\n",
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True, exist_ok=True)
    return repo


def _seed(*, labels: list[str]) -> None:
    _ = make_beads_client(config=_config(repo=Path("/nonexistent"))).create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="task",
            title="The spec-change tier",
            description="Prose.",
            priority=2,
            assignee=None,
            created_at="2026-10-24T00:00:00Z",
            labels=labels,
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )


class _Recording:
    """A reader that records the topic it was asked about."""

    def __init__(self) -> None:
        self.topics: list[str | None] = []

    def __call__(
        self, *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        _ = (item, repo, topic_ratified)
        self.topics.append(linked_topic)
        return None


class _Unreadable:
    """A beads client whose every read refuses."""

    def show_issue(self, *, issue_id: str) -> dict[str, object]:
        raise BeadsConnectionError(detail=f"tenant unreachable for {issue_id}")


class _Sparse:
    """A beads client answering the `omitempty` shape of a label-less record."""

    def show_issue(self, *, issue_id: str) -> dict[str, object]:
        return {"id": issue_id, "status": "ready"}


def _unreadable_client(*, config: StoreConfig) -> _Unreadable:
    """A client factory standing in for one whose tenant refuses every read."""
    _ = config
    return _Unreadable()


def _sparse_client(*, config: StoreConfig) -> _Sparse:
    """A client factory standing in for one answering `omitempty`-sparse records."""
    _ = config
    return _Sparse()


def _asked_topic(*, tmp_path: Path, labels: list[str]) -> list[str | None]:
    _seed(labels=labels)
    reader = _Recording()
    _ = spec_change_tier_hold(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        path=_config(repo=_repo(tmp_path=tmp_path)),
        stage="pre-admission",
        reader=reader,
    )
    return reader.topics


def test_a_declared_topic_label_reaches_the_classification(tmp_path: Path) -> None:
    """The control: the read genuinely resolves a topic off the item's labels."""
    assert _asked_topic(tmp_path=tmp_path, labels=[f"proposal-topic:{_TOPIC}"]) == [_TOPIC]


def test_an_item_declaring_no_topic_label_is_classified_with_none(tmp_path: Path) -> None:
    """The ordinary case: a well-formed record carrying other labels only."""
    assert _asked_topic(tmp_path=tmp_path, labels=["intake:triaged"]) == [None]


def test_a_ledger_read_that_refuses_is_classified_with_no_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient ledger fault must not refuse a dispatch, nor raise through it."""
    _seed(labels=[f"proposal-topic:{_TOPIC}"])
    monkeypatch.setattr(_spec_change_tier_gate, "make_beads_client", _unreadable_client)
    reader = _Recording()

    _ = spec_change_tier_hold(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        path=_config(repo=_repo(tmp_path=tmp_path)),
        stage="pre-admission",
        reader=reader,
    )

    assert reader.topics == [None]


def test_a_record_carrying_no_labels_key_at_all_is_classified_with_no_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `omitempty` sparse shape, which a key-indexing reader raises on."""
    _seed(labels=[f"proposal-topic:{_TOPIC}"])
    monkeypatch.setattr(_spec_change_tier_gate, "make_beads_client", _sparse_client)
    reader = _Recording()

    _ = spec_change_tier_hold(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        path=_config(repo=_repo(tmp_path=tmp_path)),
        stage="pre-admission",
        reader=reader,
    )

    assert reader.topics == [None]
