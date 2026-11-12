"""The one reader of an item's operator rulings, over its ledger comments.

Recovery routing asks `_dispatcher_ruling_currency` which ruling governs an item,
so every claim about WHICH comment counts is made here, over bodies the real
writers render.

`SPECIFICATION/contracts.md`: a ruling is CURRENT "from the instant its comment is
written until the item carries a `...-consumed` comment naming it, or until a
later seed ruling or fresh ruling for the same item replaces it; the latest
ruling of either kind governs."
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_fresh_ruling import (
    fresh_ruling_comment_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ruling_currency import (
    FRESH_RULING_CONSUMED_MARKER,
    SEED_RULING_CONSUMED_MARKER,
    FreshRuling,
    current_ruling,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    SeedRuling,
    seed_ruling_comment_body,
)

_ITEM = "bd-ib-ruled"
_SHA = "b2" * 20
_FIRST = "2026-11-10T01:00:00Z"
_SECOND = "2026-11-10T02:00:00Z"


def _seed(*, ref: str = "refs/heads/rescue/x", reason: str = "checked", instant: str) -> str:
    return seed_ruling_comment_body(
        work_item_id=_ITEM,
        preservation_ref=ref,
        commit_sha=_SHA,
        invoker="coordinator",
        reason=reason,
        instant=instant,
    )


def _fresh(*, instant: str) -> str:
    return fresh_ruling_comment_body(
        work_item_id=_ITEM, invoker="coordinator", reason="start over", instant=instant
    )


def _consumed(*, marker: str, instant: str) -> str:
    return "\n".join((marker, f"ruling-instant: {instant}", "dispatch-id: d", "run-id: r"))


def test_a_rendered_seed_ruling_reads_back_as_the_ruling_it_was_written_from() -> None:
    assert current_ruling(comments=(_seed(instant=_FIRST),)) == SeedRuling(
        work_item_id=_ITEM,
        preservation_ref="refs/heads/rescue/x",
        commit_sha=_SHA,
        invoker="coordinator",
        reason="checked",
        instant=_FIRST,
    )


def test_a_rendered_fresh_ruling_reads_back_as_the_ruling_it_was_written_from() -> None:
    assert current_ruling(comments=(_fresh(instant=_FIRST),)) == FreshRuling(
        work_item_id=_ITEM, invoker="coordinator", reason="start over", instant=_FIRST
    )


def test_no_comment_and_unrelated_comments_carry_no_ruling() -> None:
    assert current_ruling(comments=()) is None
    assert current_ruling(comments=("Rider: keep the scope small.", "")) is None


@pytest.mark.parametrize(
    "dropped",
    ["work-item", "preservation-ref", "commit-sha", "invoker", "reason", "instant"],
)
def test_a_seed_ruling_body_missing_a_field_is_inert_rather_than_half_read(*, dropped: str) -> None:
    lines = _seed(instant=_FIRST).splitlines()
    kept = [line for line in lines if not line.startswith(f"{dropped}: ")]

    assert current_ruling(comments=("\n".join(kept),)) is None


@pytest.mark.parametrize("dropped", ["work-item", "invoker", "reason", "instant"])
def test_a_fresh_ruling_body_missing_a_field_is_inert_rather_than_half_read(
    *, dropped: str
) -> None:
    lines = _fresh(instant=_FIRST).splitlines()
    kept = [line for line in lines if not line.startswith(f"{dropped}: ")]

    assert current_ruling(comments=("\n".join(kept),)) is None


def test_a_ruling_with_an_empty_instant_is_inert() -> None:
    assert current_ruling(comments=(_seed(instant=""),)) is None


def test_a_reason_shaped_like_a_field_cannot_overwrite_the_real_one() -> None:
    forged = _seed(
        reason="looks fine\nsecond line without a field\ncommit-sha: "
        + "c3" * 20
        + "\npreservation-ref: refs/heads/forged",
        instant=_FIRST,
    )

    ruling = current_ruling(comments=(forged,))

    assert isinstance(ruling, SeedRuling)
    assert ruling.commit_sha == _SHA
    assert ruling.preservation_ref == "refs/heads/rescue/x"


def test_the_later_of_two_seed_rulings_governs() -> None:
    comments = (
        _seed(ref="refs/heads/rescue/first", instant=_FIRST),
        _seed(ref="refs/heads/rescue/second", instant=_SECOND),
    )

    ruling = current_ruling(comments=comments)

    assert isinstance(ruling, SeedRuling)
    assert ruling.preservation_ref == "refs/heads/rescue/second"


def test_the_latest_ruling_of_either_kind_governs() -> None:
    seed_then_fresh = current_ruling(comments=(_seed(instant=_FIRST), _fresh(instant=_SECOND)))
    fresh_then_seed = current_ruling(comments=(_fresh(instant=_FIRST), _seed(instant=_SECOND)))

    assert isinstance(seed_then_fresh, FreshRuling)
    assert isinstance(fresh_then_seed, SeedRuling)


def test_the_newer_ruling_governs_when_the_ledger_returns_comments_newest_first() -> None:
    """The durable ruling instant, rather than an API listing order, decides currency."""
    ruling = current_ruling(comments=(_fresh(instant=_SECOND), _seed(instant=_FIRST)))

    assert isinstance(ruling, FreshRuling)
    assert ruling.instant == _SECOND


@pytest.mark.parametrize(
    ("ruling", "marker"),
    [
        (_seed(instant=_FIRST), SEED_RULING_CONSUMED_MARKER),
        (_fresh(instant=_FIRST), FRESH_RULING_CONSUMED_MARKER),
    ],
    ids=["seed", "fresh"],
)
def test_a_ruling_the_item_carries_a_consumed_comment_for_no_longer_governs(
    ruling: str, marker: str
) -> None:
    assert current_ruling(comments=(ruling, _consumed(marker=marker, instant=_FIRST))) is None


def test_a_consumed_comment_names_one_ruling_by_kind_and_instant() -> None:
    seed = _seed(instant=_FIRST)

    # Another ruling's instant, and the other kind's marker at the same instant.
    assert current_ruling(
        comments=(seed, _consumed(marker=SEED_RULING_CONSUMED_MARKER, instant=_SECOND))
    ) == current_ruling(comments=(seed,))
    assert isinstance(
        current_ruling(
            comments=(seed, _consumed(marker=FRESH_RULING_CONSUMED_MARKER, instant=_FIRST))
        ),
        SeedRuling,
    )
    # A consumed comment with no field naming the instant at all.
    assert isinstance(
        current_ruling(comments=(seed, SEED_RULING_CONSUMED_MARKER + "\nrun-id: r")), SeedRuling
    )


def test_a_consumed_later_ruling_does_not_revive_the_earlier_one_it_replaced() -> None:
    comments = (
        _seed(ref="refs/heads/rescue/first", instant=_FIRST),
        _seed(ref="refs/heads/rescue/second", instant=_SECOND),
        _consumed(marker=SEED_RULING_CONSUMED_MARKER, instant=_SECOND),
    )

    assert current_ruling(comments=comments) is None
