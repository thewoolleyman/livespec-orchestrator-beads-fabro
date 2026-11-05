"""The refresh repair preserves the implement-stage timeout alias."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts


def test_red_and_green_keep_the_implement_timeout_after_refresh_repair() -> None:
    """Both fresh agent nodes resolve the established `implement` setting."""
    timeouts = NodeTimeouts(
        configured={"implement": 7200},
        stall_seconds=7200,
        stall_layer="default",
    )
    assert timeouts.seconds_for(node="red") == 7200
    assert timeouts.seconds_for(node="green") == 7200
