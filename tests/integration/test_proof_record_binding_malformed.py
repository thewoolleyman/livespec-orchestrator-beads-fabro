"""The binding reader rejects a duplicate or misplaced binding line."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_binding import (
    proof_record_inventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records


def test_malformed_binding_lines_are_unbindable() -> None:
    """Every record with a Binds line gets a single, fail-closed verdict."""
    records = proof_records(
        comments=[
            {
                "url": "duplicate",
                "body": (
                    "Proof of Done — verified — run r — t\n"
                    "Binds: bd-ib-poh6jg — pull request #1 — head " + "a" * 40 + "\n"
                    "Binds: bd-ib-poh6jg — pull request #1 — head " + "a" * 40
                ),
            },
            {
                "url": "misplaced",
                "body": (
                    "Proof of Done — verified — run r — t\n\n"
                    "Binds: bd-ib-poh6jg — pull request #1 — head " + "a" * 40
                ),
            },
        ]
    )

    inventory = proof_record_inventory(
        records=records,
        work_item_id="bd-ib-poh6jg",
        pull_request=1,
        merged_head="a" * 40,
        dispatch_ids=("r",),
    )

    assert [entry.verdict for entry in inventory.entries] == ["unbindable", "unbindable"]
    assert [entry.fault for entry in inventory.entries] == [
        "record carries more than one Binds line",
        "Binds line is not immediately after the record header",
    ]
