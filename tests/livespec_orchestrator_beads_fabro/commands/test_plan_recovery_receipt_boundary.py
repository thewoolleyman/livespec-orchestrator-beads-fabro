"""The causal-recovery receipt writer is available to executor boundaries."""

from __future__ import annotations

import importlib


def test_receipt_writer_exposes_executor_owned_recording() -> None:
    """Executors receive a dedicated transition writer, not metadata access."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._plan_recovery_receipt_write"
    )

    assert hasattr(module, "record_recovery_receipts")
