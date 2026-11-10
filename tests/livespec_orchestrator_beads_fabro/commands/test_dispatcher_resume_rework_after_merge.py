"""The reading that orders a rework rejection against a pull request's merge.

`bd-ib-nkoyln`. The routing case in
`test_dispatcher_recovery_routing_rework_after_merge.py` drives the whole ladder;
these cover the decisions that case cannot reach one at a time: each unreadable
shape of the two instants, the timezone-less stamp, and the forge listing carrying
the merge instant through to the observation.

EVERY UNREADABLE SHAPE IS ASSERTED AS "NOT AFTER THE MERGE", beside a positive
case on the same fixture, because a reading that answered `True` for everything
would satisfy a lone rework-after-merge case exactly as well as a correct one.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_forge import (
    branch_pull_request_argv,
    branch_pull_request_from_stdout,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_rework_after_merge import (
    rework_rejected_after_merge,
)

_ITEM = "bd-ib-5d5aue"
_MERGED = "2026-11-03T12:00:00Z"
_HUMAN = "human-valve-reject-rework"


def _row(*, at: object, stage: str = _HUMAN, item: str = _ITEM) -> dict[str, object]:
    return {"stage": stage, "work_item_id": item, "at": at}


def test_a_later_rejection_postdates_the_merge_and_an_earlier_one_does_not() -> None:
    later = _row(at="2026-11-04T09:48:12Z")
    earlier = _row(at="2026-11-02T09:48:12Z")
    assert rework_rejected_after_merge(records=[later], work_item_id=_ITEM, merged_at=_MERGED)
    assert not rework_rejected_after_merge(records=[earlier], work_item_id=_ITEM, merged_at=_MERGED)
    assert rework_rejected_after_merge(
        records=[earlier, later], work_item_id=_ITEM, merged_at=_MERGED
    )


def test_a_stamp_without_a_zone_is_read_as_utc() -> None:
    naive = _row(at="2026-11-04T09:48:12")
    assert rework_rejected_after_merge(records=[naive], work_item_id=_ITEM, merged_at=_MERGED)
    assert rework_rejected_after_merge(
        records=[_row(at="2026-11-04T09:48:12Z")],
        work_item_id=_ITEM,
        merged_at="2026-11-03T12:00:00",
    )


def test_an_unreadable_merge_instant_is_never_before_a_rejection() -> None:
    later = _row(at="2026-11-04T09:48:12Z")
    assert not rework_rejected_after_merge(records=[later], work_item_id=_ITEM, merged_at=None)
    assert not rework_rejected_after_merge(records=[later], work_item_id=_ITEM, merged_at="soon")


def test_an_unreadable_rejection_instant_is_not_after_the_merge() -> None:
    for at in (None, 12, "yesterday"):
        assert not rework_rejected_after_merge(
            records=[_row(at=at)], work_item_id=_ITEM, merged_at=_MERGED
        )


def test_only_the_two_rework_entries_of_this_item_count() -> None:
    at = "2026-11-04T09:48:12Z"
    auto = {"stage": "auto-disposition", "disposition": "ai-fail-auto-rework"}
    other_disposition = {"stage": "auto-disposition", "disposition": "ai-pass-auto-accept"}
    assert rework_rejected_after_merge(
        records=[{**auto, "work_item_id": _ITEM, "at": at}], work_item_id=_ITEM, merged_at=_MERGED
    )
    for record in (
        {**other_disposition, "work_item_id": _ITEM, "at": at},
        _row(at=at, stage="human-valve-reject-regroom"),
        _row(at=at, item="bd-ib-other"),
    ):
        assert not rework_rejected_after_merge(
            records=[record], work_item_id=_ITEM, merged_at=_MERGED
        )


def test_the_listing_asks_for_and_carries_the_merge_instant() -> None:
    assert "number,state,headRefOid,mergedAt" in branch_pull_request_argv(branch="feat/x")
    merged = branch_pull_request_from_stdout(
        stdout='[{"number": 1, "state": "MERGED", "headRefOid": "a", "mergedAt": "2026-11-03T12:00:00Z"}]'
    )
    assert merged.pull_request is not None
    assert merged.pull_request.merged_at == "2026-11-03T12:00:00Z"
    for raw in ('"mergedAt": ""', '"mergedAt": 5', '"other": 1'):
        read = branch_pull_request_from_stdout(
            stdout=f'[{{"number": 1, "state": "OPEN", "headRefOid": "a", {raw}}}]'
        )
        assert read.pull_request is not None
        assert read.pull_request.merged_at is None
