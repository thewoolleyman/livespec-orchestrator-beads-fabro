"""The narrow predicate that lets reconciliation enforce a lost watch's wall budget.

The wall clock applies only after the factory reports a run is occupying a
slot and the claim survey has established that no local dispatcher owns it.
Keeping that predicate separate prevents a failed ownership measurement from
being mistaken for permission to cancel a still-observed dispatch.
"""

from __future__ import annotations

__all__: list[str] = ["should_enforce_wall_budget"]


def should_enforce_wall_budget(
    *,
    run_status: str | None,
    owner_liveness: str,
    elapsed_seconds: float | None,
    budget_seconds: float,
) -> bool:
    """Whether reconciliation may hand this live run to the wall-budget cancel.

    Only a running run holds a factory slot.  A missing clock or an unreadable
    ownership reading is not evidence for cancellation, and equality remains
    within budget just as it is in the dispatch watch.
    """
    return (
        run_status == "running"
        and owner_liveness == "none"
        and elapsed_seconds is not None
        and elapsed_seconds > budget_seconds
    )
