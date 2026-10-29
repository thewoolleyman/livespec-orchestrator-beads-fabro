"""The `check` command's summary of one inventory snapshot."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import InventorySnapshot

__all__: list[str] = [
    "check_summary",
]


def check_summary(*, snapshot: InventorySnapshot) -> dict[str, object]:
    """Every outstanding mismatch as its own entry, so none hides in a row scan."""
    findings = [
        {
            "finding": finding,
            "id": record.wait_id,
            "record_state": record.record_state,
            "source": "wait",
        }
        for record in snapshot.records
        for finding in sorted(record.findings)
    ]
    return {"findings": findings, "healthy": not findings}
