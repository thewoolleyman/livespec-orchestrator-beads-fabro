"""Dispatch identity joins ACP selections to the run that executed them."""

from __future__ import annotations

import inspect

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    selection_warning_records,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    acp_node_selection_record,
)


def test_dispatch_identity_joins_a_selection_to_its_own_run() -> None:
    """A later same-item selection cannot be attributed to an earlier run."""
    assert "dispatch_id" in inspect.signature(acp_node_selection_record).parameters
    assert (
        acp_node_selection_record(selected={}, dispatch_id="dispatch-2")["dispatch_id"]
        == "dispatch-2"
    )
    records = (
        {
            "at": "2026-10-19T00:00:00Z",
            "stage": "acp-node-selection",
            "work_item_id": "item",
            "dispatch_id": "dispatch-1",
            "selections": {"implement": _fallback_selection()},
        },
        {
            "stage": "dispatch-run-stamp",
            "work_item_id": "item",
            "dispatch_id": "dispatch-1",
            "run_id": "run-1",
        },
        {
            "at": "2026-10-19T00:01:00Z",
            "stage": "acp-node-selection",
            "work_item_id": "item",
            "dispatch_id": "dispatch-2",
            "selections": {"implement": {**_fallback_selection(), "selected_index": 0}},
        },
    )
    warnings = selection_warning_records(
        records=records,
        work_item_id="item",
        run_id="run-1",
        outcomes={"implement": {"status": "succeeded"}},
    )
    assert warnings is not None
    assert [warning["event_id"] for warning in warnings] == ["selection:run-1:selection-1"]


def _fallback_selection() -> dict[str, object]:
    """One complete non-primary selection record."""
    return {
        "selection_identity": "selection-1",
        "selected_index": 1,
        "selected_candidate_key": "fallback",
        "selected_availability_key": "availability",
        "primary_generation_digest": "primary-1",
        "full_chain_digest": "chain-1",
    }
