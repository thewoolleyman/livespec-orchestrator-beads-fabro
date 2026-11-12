"""Render deferred outcomes for recovery routes held before admission."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    RECOVERY_HELD_STAGE,
    recovery_held_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_HELD,
    RecoveryRoute,
)

__all__: list[str] = ["held_outcomes"]


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
