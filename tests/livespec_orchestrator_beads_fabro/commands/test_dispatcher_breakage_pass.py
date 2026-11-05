"""Acceptance surface for the scheduled-workflow breakage pass."""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher


def test_breakage_pass_is_a_dispatcher_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 313 starts the host-side filing pass through this CLI surface."""

    def run_breakage_pass(*, args: Any) -> int:
        assert args.subcommand == "breakage-pass"
        return 0

    monkeypatch.setitem(
        dispatcher.__dict__, "_SUBCOMMAND_HANDLERS", {"breakage-pass": run_breakage_pass}
    )

    assert dispatcher.main(argv=["breakage-pass"]) == 0
