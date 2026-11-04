"""Tolerance coverage for selection-derived fallback records."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    selection_warning_records,
)


@pytest.mark.parametrize(
    ("records", "outcomes"),
    [
        ((), {"implement": {"status": "succeeded"}}),
        (({"stage": "acp-node-selection", "work_item_id": "item"},), {"implement": {}}),
        (
            (
                {
                    "at": " ",
                    "stage": "acp-node-selection",
                    "work_item_id": "item",
                    "selections": {},
                },
            ),
            {"implement": {}},
        ),
        (
            (
                {
                    "at": "2026-10-19T00:00:00Z",
                    "stage": "acp-node-selection",
                    "work_item_id": "item",
                    "selections": {"implement": "not-a-map"},
                },
            ),
            {"implement": {}},
        ),
    ],
)
def test_sparse_or_malformed_selections_mint_no_warning(
    records: tuple[dict[str, object], ...], outcomes: dict[str, dict[str, object]]
) -> None:
    """Unreadable selection fields are not guessed into fallback evidence."""
    assert (
        selection_warning_records(
            records=records,
            work_item_id="item",
            run_id="run",
            outcomes=outcomes,
        )
        == ()
    )


@pytest.mark.parametrize("index", [False, 0, -1, "1"])
def test_non_fallback_or_invalid_selection_positions_mint_no_warning(index: object) -> None:
    """Only a positive, integral selected position is a fallback."""
    assert (
        selection_warning_records(
            records=(
                {
                    "at": "2026-10-19T00:00:00Z",
                    "stage": "acp-node-selection",
                    "work_item_id": "item",
                    "selections": {
                        "implement": {
                            "selection_identity": "identity",
                            "selected_index": index,
                            "selected_candidate_key": "candidate",
                            "selected_availability_key": "availability",
                            "primary_generation_digest": "primary",
                            "full_chain_digest": "chain",
                        }
                    },
                },
            ),
            work_item_id="item",
            run_id="run",
            outcomes={"implement": {}},
        )
        == ()
    )


@pytest.mark.parametrize(
    "field",
    [
        "selection_identity",
        "selected_candidate_key",
        "selected_availability_key",
        "primary_generation_digest",
        "full_chain_digest",
    ],
)
def test_incomplete_selection_identity_mints_no_warning(field: str) -> None:
    """A warning needs every stable identity needed by the legacy record."""
    choice: dict[str, object] = {
        "selection_identity": "identity",
        "selected_index": 1,
        "selected_candidate_key": "candidate",
        "selected_availability_key": "availability",
        "primary_generation_digest": "primary",
        "full_chain_digest": "chain",
    }
    choice[field] = " "
    assert (
        selection_warning_records(
            records=(
                {
                    "at": "2026-10-19T00:00:00Z",
                    "stage": "acp-node-selection",
                    "work_item_id": "item",
                    "selections": {"implement": choice},
                },
            ),
            work_item_id="item",
            run_id="run",
            outcomes={"implement": {}},
        )
        == ()
    )


def test_selection_lookup_ignores_a_later_record_for_another_item() -> None:
    """A journal can interleave dispatches without changing the selected row."""
    selection = {
        "at": "2026-10-19T00:00:00Z",
        "stage": "acp-node-selection",
        "work_item_id": "item",
        "selections": {
            "implement": {
                "selection_identity": "identity",
                "selected_index": 0,
                "selected_candidate_key": "candidate",
                "selected_availability_key": "availability",
                "primary_generation_digest": "primary",
                "full_chain_digest": "chain",
            }
        },
    }
    assert (
        selection_warning_records(
            records=(selection, {"stage": "acp-node-selection", "work_item_id": "other"}),
            work_item_id="item",
            run_id="run",
            outcomes={"implement": {}},
        )
        == ()
    )
