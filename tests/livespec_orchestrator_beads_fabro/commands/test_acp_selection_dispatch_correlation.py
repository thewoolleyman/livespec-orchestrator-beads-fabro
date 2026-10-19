"""Selection records retain the dispatch identity that launched them."""

from __future__ import annotations

import inspect

from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    acp_node_selection_record,
)


def test_selection_record_carries_its_launching_dispatch_id() -> None:
    """Same-item re-dispatches are joined by identity, never journal order."""
    assert "dispatch_id" in inspect.signature(acp_node_selection_record).parameters
    record = acp_node_selection_record(selected={}, dispatch_id="dispatch-123")
    assert record["dispatch_id"] == "dispatch-123"
