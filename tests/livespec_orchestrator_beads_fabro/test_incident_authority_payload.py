"""Incident authority payload decoding."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    decode_attempt,
    unsupported_carrier,
)


def test_drill_closed_is_a_decodable_terminal_incident_phase() -> None:
    attempt = decode_attempt(
        value={
            "repository": "owner/repository",
            "item_id": "bd-ib-drill",
            "attempt_id": "drill-1",
            "phase": "drill-closed",
            "operation_id": "drill-1#drill-close",
            "generation": 2,
            "owner": "operator:alice",
            "base": "a" * 40,
            "head": "b" * 40,
            "pr_number": 7,
            "landed_commits": [],
            "landed_trees": [],
            "original_paths": ["app.py"],
            "deferred_work": ["normal-factory-proof"],
            "repayment_required": False,
        }
    )

    assert attempt is not None and attempt.phase == "drill-closed"
    assert not unsupported_carrier(value=None)
