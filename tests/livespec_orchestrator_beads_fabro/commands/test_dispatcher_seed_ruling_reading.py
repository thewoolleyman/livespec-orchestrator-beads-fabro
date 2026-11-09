"""Parsing boundaries for the durable ruled-seed ledger comment."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    latest_unconsumed_seed_ruling,
)


def test_unrelated_and_incomplete_comments_do_not_become_seed_instructions() -> None:
    """Only the complete marker-body grammar has authority over recovery."""
    assert (
        latest_unconsumed_seed_ruling(
            comments=("", "operator rider", "livespec-seed-ruling\nwork-item: bd-ib-ltlg4i"),
            consumed_instants=frozenset(),
        )
        is None
    )


def test_a_consumed_ruling_is_not_selected_again() -> None:
    """Consumption is keyed by the instant the immutable ruling recorded."""
    instant = "2026-11-05T18:00:00Z"
    body = "\n".join(
        (
            "livespec-seed-ruling",
            "work-item: bd-ib-ltlg4i",
            "preservation-ref: refs/heads/needs-human/older-run",
            f"commit-sha: {'a' * 40}",
            "invoker: coordinator",
            "reason: retain the tree",
            f"instant: {instant}",
        )
    )

    assert (
        latest_unconsumed_seed_ruling(comments=(body,), consumed_instants=frozenset({instant}))
        is None
    )
