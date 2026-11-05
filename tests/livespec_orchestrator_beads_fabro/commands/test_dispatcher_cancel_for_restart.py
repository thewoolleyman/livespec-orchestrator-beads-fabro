"""The factory-restart cancellation route preserves green trees first."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher


def test_cancel_for_restart_is_a_public_dispatcher_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator route is explicit instead of a raw factory-server cancel."""
    assert hasattr(dispatcher, "run_cancel_for_restart_command")
    received: list[object] = []

    def _handler(*, args: object) -> int:
        received.append(args)
        return 0

    monkeypatch.setattr(dispatcher, "run_cancel_for_restart_command", _handler)
    assert dispatcher.main(argv=["cancel-for-restart", "--factory", "petri"]) == 0
    assert received[0].factory == "petri"
    assert received[0].repo is None
