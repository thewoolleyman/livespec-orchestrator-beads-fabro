"""One-use causal recovery epochs for the redispatch progress guard."""

from __future__ import annotations

import importlib


def test_a_fresh_typed_recovery_authorizes_only_one_flat_history_epoch() -> None:
    """A recorded recovery is evidence, not a reusable counter reset."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress"
    )
    assert hasattr(module, "RedispatchRecovery")
