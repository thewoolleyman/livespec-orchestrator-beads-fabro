"""Warnings derived from the Dispatcher's selection record and run outcomes."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _acp_fallback_warning_ledger as ledger


def test_a_non_primary_selection_that_the_run_executed_mints_one_warning() -> None:
    """The selection record, not an engine failover event, is the warning source."""
    assert hasattr(ledger, "selection_warning_records")
    records = (
        {
            "at": "2026-10-18T20:00:00Z",
            "stage": "acp-node-selection",
            "work_item_id": "bd-ib-augqc2",
            "selections": {
                "implement": {
                    "selection_identity": "selection-1",
                    "selected_index": 1,
                    "selected_candidate_key": "claude-haiku",
                    "selected_availability_key": "anthropic",
                    "primary_generation_digest": "primary-1",
                    "full_chain_digest": "chain-1",
                }
            },
        },
    )
    warnings = ledger.selection_warning_records(
        records=records,
        work_item_id="bd-ib-augqc2",
        run_id="01RUN",
        outcomes={"implement": {"status": "succeeded"}},
    )
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["node"] == "implement"
    assert warning["candidate_index"] == 1
    assert warning["event_id"] == "selection:01RUN:selection-1"
    assert warning["primary_generation"] == "primary-1"
    assert warning["full_chain"] == "chain-1"


def test_missing_node_outcomes_are_unavailable_not_an_unexecuted_node(tmp_path: Path) -> None:
    """An empty outcome map cannot erase an existing warning by implication."""
    del tmp_path
    assert hasattr(ledger, "selection_warning_records")
    assert (
        ledger.selection_warning_records(
            records=(), work_item_id="bd-ib-augqc2", run_id="01RUN", outcomes={}
        )
        is None
    )
