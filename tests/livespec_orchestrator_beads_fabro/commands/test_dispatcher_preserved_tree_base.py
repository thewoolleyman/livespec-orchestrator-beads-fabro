"""The base commit the preservation commit is parented on, as the dispatch named it."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import (
    SOURCE_STAGE,
    run_base_commit,
)

_ITEM = "bd-ib-na2xvm"
_FIRST = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_SECOND = "c7040c03bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _staged(*, work_item_id: str, staged_at: object) -> dict[str, object]:
    return {"stage": SOURCE_STAGE, "work_item_id": work_item_id, "staged_at": staged_at}


def test_the_base_commit_is_the_commit_this_item_s_sandbox_was_staged_at() -> None:
    # The two rows that must be passed over sit AFTER this item's staging row,
    # because the reading runs newest-first: a journal whose only distractors
    # preceded the answer would never reach either skip, and the reader could
    # drop both while still passing.
    assert (
        run_base_commit(
            records=(
                _staged(work_item_id=_ITEM, staged_at=_FIRST),
                {"stage": "outcome", "work_item_id": _ITEM},
                _staged(work_item_id="bd-ib-other", staged_at=_SECOND),
            ),
            work_item_id=_ITEM,
        )
        == _FIRST
    )


def test_another_item_s_staging_row_is_never_this_item_s_base() -> None:
    # One journal carries every item the drain dispatched in that pass, so a
    # reader that took the newest staging row of ANY item would parent this
    # item's preserved tree on another item's base -- a recovery artifact whose
    # diff is against the wrong commit, which reads as plausible work.
    assert (
        run_base_commit(
            records=(_staged(work_item_id="bd-ib-other", staged_at=_FIRST),),
            work_item_id=_ITEM,
        )
        is None
    )


def test_a_re_dispatch_takes_the_latest_staging_row_for_the_item() -> None:
    # A re-dispatch of one item appends a second staging row to the same
    # journal, and THIS run's base is the last one staged. Taking the first
    # would parent the tree on the base of a dispatch that has already ended.
    assert (
        run_base_commit(
            records=(
                _staged(work_item_id=_ITEM, staged_at=_FIRST),
                _staged(work_item_id=_ITEM, staged_at=_SECOND),
            ),
            work_item_id=_ITEM,
        )
        == _SECOND
    )


def test_a_row_naming_no_commit_is_not_a_base_and_does_not_mask_an_earlier_one() -> None:
    # A staging row whose `staged_at` is absent, empty or not a string is a row
    # that could not establish the base. It must not be read as the answer --
    # the empty string would reach the forge as a parent -- and it must not hide
    # a row that DID establish one, because the clause requires the publication
    # to be attempted wherever the base is knowable.
    for unnamed in (None, "", "   ", 5):
        assert (
            run_base_commit(
                records=(
                    _staged(work_item_id=_ITEM, staged_at=_FIRST),
                    _staged(work_item_id=_ITEM, staged_at=unnamed),
                ),
                work_item_id=_ITEM,
            )
            == _FIRST
        ), unnamed


def test_a_journal_with_no_staging_row_names_no_base() -> None:
    assert run_base_commit(records=(), work_item_id=_ITEM) is None
