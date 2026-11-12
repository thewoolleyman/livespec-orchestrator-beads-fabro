"""Deferred outcome and report rendering for recovery-held routes."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_held_outcomes import (
    held_outcomes,
    is_held,
    recovery_held_route_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    RecoveryHold,
    RecoveryRoute,
)


def test_held_routes_render_deferred_outcomes_and_reports() -> None:
    """One held route supplies the journal outcome and the operator report."""
    held = RecoveryRoute(
        work_item_id="bd-ib-p6ammc",
        route=ROUTE_HELD,
        hold=RecoveryHold(refusals=("recapture-exhausted",)),
    )
    fresh = RecoveryRoute(work_item_id="bd-ib-fresh", route=ROUTE_FRESH)

    outcomes = held_outcomes(routes=(held, fresh))

    assert [(one.work_item_id, one.status) for one in outcomes] == [
        ("bd-ib-p6ammc", "capacity-deferred")
    ]
    assert is_held(route=held)
    assert not is_held(route=fresh)
    assert not is_held(route=None)
    report = recovery_held_route_report(work_item_id="bd-ib-p6ammc", routes=(held, fresh))
    assert report is not None
    assert "recapture-exhausted" in report


def test_a_missing_or_payloadless_route_has_no_held_report() -> None:
    """The defensive reporting arm leaves non-held routes unreported."""
    payloadless = RecoveryRoute(work_item_id="bd-ib-p6ammc", route=ROUTE_HELD)

    assert recovery_held_route_report(work_item_id="missing", routes=(payloadless,)) is None
    assert recovery_held_route_report(work_item_id="bd-ib-p6ammc", routes=(payloadless,)) is None
