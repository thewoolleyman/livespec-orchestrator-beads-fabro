"""What a budget cancel says about a run that had already published.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": the `run-wall-budget-exceeded` record carries the pull
request and published head "under the same rules" as the stall cancel record,
and the item's ledger comment MUST name them too "when the record names them".

WHY BOTH SURFACES. The record is a per-clone journal file and the run record is
pruned, so the COMMENT is the only durable surface still naming the publication
once the dispatching clone is gone -- and the publication is exactly what a
person deciding how to recover needs, because a re-dispatch that does not know
about it reclaims the publish branch and deletes the head nobody named.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_comment import (
    run_wall_budget_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
    run_wall_budget_exceeded_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RUN_RECORD_SOURCE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_comments import (
    UNREAD_CANCEL_ROW,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    UNREADABLE_PUBLISHED_HEAD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    StallPublication,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_ITEM_ID = "bd-ib-budgetpub"
_RUN_ID = "01BUDGETRUN"
_HEAD = "a" * 40
_PULL_REQUEST = 2714
_BUDGET = RunWallBudget(seconds=21600.0, layer=REPOSITORY_LAYER)


def _record(*, publication: StallPublication | None) -> dict[str, object]:
    return run_wall_budget_exceeded_record(
        work_item_id=_ITEM_ID,
        dispatch_id="dispatch-01",
        run_id=_RUN_ID,
        factory="hp",
        executing_stage="proof_capture",
        publication=publication,
        elapsed_seconds=25200.0,
        budget=_BUDGET,
        start_source=RUN_RECORD_SOURCE,
        preserved_pointer="comment-9173",
    )


def _comment_for(*, publication: StallPublication | None) -> str:
    """The comment rendered from the record this cancel would have journaled.

    Routed through the record rather than a hand-built row, so the two surfaces
    are asserted against ONE reading: a comment built from fields the record
    does not actually write would pass while naming nothing an operator could
    find.
    """
    row = json.loads(json.dumps(_record(publication=publication)))
    return run_wall_budget_comment(item_id=_ITEM_ID, row=row)


def test_a_published_run_names_its_pull_request_and_head_on_both_surfaces() -> None:
    """The record and the comment name the same publication."""
    publication = StallPublication(pull_request=_PULL_REQUEST, published_head=_HEAD)
    record = _record(publication=publication)
    assert record["stage"] == RUN_WALL_BUDGET_EXCEEDED_STAGE
    assert record["pull_request"] == _PULL_REQUEST
    assert record["published_head"] == _HEAD
    body = _comment_for(publication=publication)
    assert str(_PULL_REQUEST) in body
    assert _HEAD in body


def test_an_unreadable_head_is_stated_in_the_comment_too() -> None:
    """A publication whose head could not be read says so on the ledger.

    The statement rather than a blank, because the resume ladder's remedy for
    no head is a PLAIN dispatch -- which reclaims the publish branch and
    deletes the head nobody could name. A comment that simply omitted the head
    would advise exactly that.
    """
    publication = StallPublication(pull_request=_PULL_REQUEST, published_head=None)
    body = _comment_for(publication=publication)
    assert str(_PULL_REQUEST) in body
    assert UNREADABLE_PUBLISHED_HEAD in body


def test_an_unpublished_run_says_it_completed_no_publish_draft() -> None:
    """No publication is stated as such, never left for a reader to infer.

    A comment silent about publication reads the same whether the run published
    nothing or the row could not be read, and the two support opposite
    recoveries.
    """
    body = _comment_for(publication=None)
    assert "no publish_draft" in body
    assert _HEAD not in body
    assert UNREADABLE_PUBLISHED_HEAD not in body


def test_an_unread_row_states_the_publication_as_unread() -> None:
    """A dispatch that journalled no cancel row says so about the publication."""
    body = run_wall_budget_comment(item_id=_ITEM_ID, row=None)
    assert UNREAD_CANCEL_ROW in body
    assert "no publish_draft" not in body


def test_the_comment_keeps_every_fact_the_rest_state_already_named() -> None:
    """Adding the publication does not displace the measurement or the remedy."""
    body = _comment_for(
        publication=StallPublication(pull_request=_PULL_REQUEST, published_head=_HEAD)
    )
    assert _RUN_ID in body
    assert "proof_capture" in body
    assert "25200" in body
    assert "21600" in body
    assert "comment-9173" in body
    assert f"resolve-blocked:{_ITEM_ID}:ready" in body


def test_a_row_whose_pull_request_is_unreadable_states_that_one_fact_as_unread() -> None:
    """A value neither reader can render reports the failed reading, not a value.

    And it reports ONLY that fact: the head beside it is still perfectly
    readable, so one unreadable field must not suppress the other -- a comment
    that went silent about the whole publication would read as a run that
    published nothing.
    """
    row = dict(_record(publication=StallPublication(pull_request=None, published_head=_HEAD)))
    row["pull_request"] = ["two", "thousand"]
    body = run_wall_budget_comment(item_id=_ITEM_ID, row=row)
    assert UNREAD_CANCEL_ROW in body
    assert _HEAD in body
