"""The pure decision behind the overtaken-arming ending.

`test_dispatcher_base_advance_arming.py` drives the ending through the merge
wait, which is where the CONSECUTIVE counting lives. This covers the three
readings of ONE poll directly, which that tier cannot reach: the wait returns
on a `MERGED` view before the predicate is consulted at all, so the
non-`OPEN` arm has no route through it.

Each case varies exactly ONE reading away from the reporting triple, which is
what makes it evidence about that reading rather than about the conjunction:
a predicate that ignored any single term would pass the positive case and fail
precisely the case that drops its term.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    BASE_ADVANCED_AFTER_ARMING,
    CONSECUTIVE_CONFLICTING_REPORTS,
    base_advanced_detail,
    reports_base_advanced_after_arming,
)


def test_an_armed_open_conflicting_pull_request_reports_the_condition() -> None:
    assert (
        reports_base_advanced_after_arming(
            state="OPEN",
            auto_merge_armed=True,
            merge_state_status="DIRTY",
        )
        is True
    )


@pytest.mark.parametrize(
    ("state", "auto_merge_armed", "merge_state_status", "reading_dropped"),
    [
        ("MERGED", True, "DIRTY", "the pull request is no longer OPEN"),
        ("CLOSED", True, "DIRTY", "the pull request is no longer OPEN"),
        ("OPEN", False, "DIRTY", "nothing armed this pull request"),
        # BEHIND is the refreshable advance the wait already repairs with
        # `update-branch`. It is the reading most easily confused with DIRTY
        # and it has the opposite remedy, so it gets its own case.
        ("OPEN", True, "BEHIND", "the advance is refreshable, not conflicting"),
        ("OPEN", True, "CLEAN", "the forge reports no conflict"),
        ("OPEN", True, "BLOCKED", "the forge reports no conflict"),
        ("OPEN", True, "UNKNOWN", "the forge reported no usable mergeability"),
    ],
)
def test_dropping_any_one_reading_stops_the_report(
    *,
    state: str,
    auto_merge_armed: bool,
    merge_state_status: str,
    reading_dropped: str,
) -> None:
    assert (
        reports_base_advanced_after_arming(
            state=state,
            auto_merge_armed=auto_merge_armed,
            merge_state_status=merge_state_status,
        )
        is False
    ), reading_dropped


def test_the_ending_takes_two_consecutive_reports() -> None:
    """One report is a mergeability recomputation; two is the advance.

    The constant is asserted rather than merely imported because the whole
    transient-recomputation tolerance is this number: at 1 the ending fires on
    a single reading taken mid-recompute, and a reader raising it silently
    retires the ending for any wait whose budget is smaller.
    """
    assert CONSECUTIVE_CONFLICTING_REPORTS == 2


def test_the_detail_names_the_cause_and_leaves_the_pull_request_standing() -> None:
    detail = base_advanced_detail(work_item_id="bd-ib-overtaken")

    assert detail.startswith(f"{BASE_ADVANCED_AFTER_ARMING}:")
    assert "left as it stands" in detail
