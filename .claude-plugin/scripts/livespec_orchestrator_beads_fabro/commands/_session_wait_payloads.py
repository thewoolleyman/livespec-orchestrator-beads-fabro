"""The `check` command's summary of one inventory snapshot."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import InventorySnapshot

__all__: list[str] = [
    "check_summary",
]

_WAITER_FINDINGS_MOOT_ONCE_ACKNOWLEDGED = frozenset({"waiter-missing", "waiter-replaced"})


def check_summary(
    *, snapshot: InventorySnapshot, session_id: str | None = None
) -> dict[str, object]:
    """Every outstanding mismatch as its own entry, so none hides in a row scan.

    With `session_id`, only waits that session owns are reported.
    """
    findings = [
        {
            "finding": finding,
            "id": record.wait_id,
            "record_state": record.record_state,
            "source": "wait",
        }
        for record in snapshot.records
        if session_id is None or record.session_id == session_id
        for finding in sorted(record.findings)
        if not (record.acknowledged and finding in _WAITER_FINDINGS_MOOT_ONCE_ACKNOWLEDGED)
    ]
    return {"findings": findings, "healthy": not findings}
