"""Render deferred outcomes for recovery routes held before admission."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    RECOVERY_HELD_STAGE,
    recovery_held_detail,
    recovery_held_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_HELD,
    RecoveryRoute,
)

__all__: list[str] = ["held_outcomes", "is_held", "recovery_held_route_report"]


def held_outcomes(*, routes: tuple[RecoveryRoute, ...]) -> list[DispatchOutcome]:
    """Render one capacity-style deferred outcome for every held route."""
    return [
        DispatchOutcome(
            work_item_id=one.work_item_id,
            status="capacity-deferred",
            stage=RECOVERY_HELD_STAGE,
            pr_number=None,
            merge_sha=None,
            detail=recovery_held_detail(route=one),
        )
        for one in routes
        if one.route == ROUTE_HELD
    ]


def is_held(*, route: RecoveryRoute | None) -> bool:
    """Whether this is a held recovery route."""
    return route is not None and route.route == ROUTE_HELD


def recovery_held_route_report(
    *, work_item_id: str, routes: tuple[RecoveryRoute, ...]
) -> str | None:
    """Render the held-route refusal, or leave a live route unreported."""
    route = next((one for one in routes if one.work_item_id == work_item_id), None)
    if route is None or route.hold is None:
        return None
    return recovery_held_report(work_item_id=work_item_id, hold=route.hold)
