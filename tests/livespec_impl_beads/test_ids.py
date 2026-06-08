"""Tests for the ID generator."""

import re

from livespec_impl_beads._ids import new_memo_id, new_work_item_id


def test_new_work_item_id_shape() -> None:
    assert re.fullmatch(r"li-[a-z2-7]{6}", new_work_item_id()) is not None


def test_new_memo_id_shape() -> None:
    assert re.fullmatch(r"mm-[a-z2-7]{6}", new_memo_id()) is not None


def test_ids_are_distinct_across_calls() -> None:
    seen = {new_work_item_id() for _ in range(100)}
    assert len(seen) == 100  # collision probability is astronomically low
