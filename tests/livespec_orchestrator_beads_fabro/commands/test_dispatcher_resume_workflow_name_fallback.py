"""Which workflow a resumed run runs, read off the journal's own dispatch records.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" requires the resumed run to "run the workflow the earlier run's
dispatch record names (`workflow_name`)". The reading is a scan of the item's
`dispatch-id` records, and the cases that matter are the ones where the scan finds
a record for the item and still cannot answer.

WHY A MATCHED RECORD CARRYING NO USABLE NAME MUST NOT BE AN ANSWER. The field is
JSON a previous build wrote, so a `dispatch-id` record predating the field carries
none, and a malformed one may carry a blank or a non-string. Every one of those
readings has to leave the resumed dispatch on the ordinary variant precedence,
which resolves the item's own recorded pin and reaches the same graph. The
direction is what makes it worth asserting separately from the no-record case: a
coerced `""` or a `str()`-ed non-string would be passed to `fabro run` as a
workflow NAME, and a name that resolves to nothing dies at run-create with an
error about a variant the operator never registered.

WHY THE NEWEST WINS. An item legitimately carries several dispatches over its
life, and a resume finishes the LATEST published run. The scan therefore keeps
overwriting rather than returning on its first hit — and the test that proves it
has to put the names in journal order, because a scan that returned early would
pass against a single-record journal and against a journal whose first record
happens to be the newest.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    earlier_workflow_name,
)


def _dispatch_record(*, work_item_id: str, **fields: object) -> dict[str, object]:
    """One `dispatch-id` journal row for an item, with whatever fields a case needs."""
    return {"stage": "dispatch-id", "work_item_id": work_item_id, **fields}


def test_matched_record_without_a_workflow_name_answers_none() -> None:
    records = (_dispatch_record(work_item_id="bd-ib-one"),)

    assert earlier_workflow_name(records=records, work_item_id="bd-ib-one") is None


def test_a_blank_workflow_name_is_not_an_answer() -> None:
    records = (_dispatch_record(work_item_id="bd-ib-one", workflow_name=""),)

    assert earlier_workflow_name(records=records, work_item_id="bd-ib-one") is None


def test_a_non_string_workflow_name_is_not_an_answer() -> None:
    records = (_dispatch_record(work_item_id="bd-ib-one", workflow_name=7),)

    assert earlier_workflow_name(records=records, work_item_id="bd-ib-one") is None


def test_an_unusable_name_does_not_shadow_a_usable_one_recorded_later() -> None:
    records = (
        _dispatch_record(work_item_id="bd-ib-one", workflow_name=""),
        _dispatch_record(work_item_id="bd-ib-one", workflow_name="implement-work-item"),
    )

    assert earlier_workflow_name(records=records, work_item_id="bd-ib-one") == (
        "implement-work-item"
    )


def test_the_newest_usable_name_wins_over_an_older_one() -> None:
    records = (
        _dispatch_record(work_item_id="bd-ib-one", workflow_name="older-variant"),
        _dispatch_record(work_item_id="bd-ib-one", workflow_name="newer-variant"),
    )

    assert earlier_workflow_name(records=records, work_item_id="bd-ib-one") == "newer-variant"


def test_another_item_s_dispatch_record_is_not_this_item_s_workflow() -> None:
    records = (_dispatch_record(work_item_id="bd-ib-other", workflow_name="other-variant"),)

    assert earlier_workflow_name(records=records, work_item_id="bd-ib-one") is None
