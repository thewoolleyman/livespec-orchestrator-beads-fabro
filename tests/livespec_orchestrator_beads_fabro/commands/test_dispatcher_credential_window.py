"""The smaller-of-two governing figure, and the name it carries."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_window import (
    CREDENTIAL_USE_WINDOW_FIGURE,
    EXECUTION_ALLOWANCE_FIGURE,
    credential_use_window_seconds,
    governing_run_budget,
)


def test_the_window_is_the_queue_allowance_plus_the_wall_budget() -> None:
    """A SUM, because the queue and the run are consecutive rather than alternative."""
    assert (
        credential_use_window_seconds(
            queue_allowance_seconds=86_400, run_wall_budget_seconds=21_600
        )
        == 108_000
    )


def test_a_smaller_window_governs_and_is_named() -> None:
    governing = governing_run_budget(
        execution_allowance_seconds=902_955, credential_use_window_seconds=108_000
    )

    assert governing.seconds == 108_000
    assert governing.figure == CREDENTIAL_USE_WINDOW_FIGURE


def test_a_smaller_allowance_governs_and_is_named() -> None:
    governing = governing_run_budget(
        execution_allowance_seconds=60_000, credential_use_window_seconds=108_000
    )

    assert governing.seconds == 60_000
    assert governing.figure == EXECUTION_ALLOWANCE_FIGURE


def test_an_exact_tie_resolves_to_the_execution_allowance() -> None:
    """Equal figures are equally the smaller, so the answer is pinned for determinism.

    Asserted rather than left to the comparison's shape: a reader of the status
    surface sees one name, and a figure that alternated between two names on
    identical inputs would read as two different faults.
    """
    governing = governing_run_budget(
        execution_allowance_seconds=108_000, credential_use_window_seconds=108_000
    )

    assert governing.seconds == 108_000
    assert governing.figure == EXECUTION_ALLOWANCE_FIGURE
